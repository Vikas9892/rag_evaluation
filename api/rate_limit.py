"""Per-client rate limiting.

The API spends real money: every /query and /stream is a Groq call. CORS keeps
other people's *pages* from spending it, but nothing stops a script pointed
straight at the endpoint. This is the second half of that defence.

A token bucket per client, in process memory. That is the honest scope: it
protects one process, and two workers would each allow the full rate. A shared
limiter needs shared state — the same argument as the evaluation cache — and
until this runs on more than one process, adding Redis would buy nothing.
"""

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

from config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


@dataclass
class TokenBucketLimiter:
    """Allows `rate` requests per second with a burst of `capacity`.

    A bucket refills continuously rather than resetting on a window boundary,
    so a client cannot spend a whole window's budget at 11:59:59 and again at
    12:00:00.
    """

    rate: float
    capacity: float
    _buckets: Dict[str, _Bucket] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def check(self, key: str, now: float) -> tuple[bool, float]:
        """Consume a token. Returns (allowed, seconds until the next one)."""
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self.capacity, updated_at=now)
                self._buckets[key] = bucket

            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.rate)
            bucket.updated_at = now

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True, 0.0

            return False, (1 - bucket.tokens) / self.rate


def client_key(request: Request) -> str:
    """Who to charge for this request.

    X-Forwarded-For is honoured because the deployment sits behind a proxy and
    every request would otherwise share the proxy's address — one client would
    exhaust everyone's budget. It is spoofable, which is why this limits cost
    rather than enforcing authorisation.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_middleware(
    limiter: TokenBucketLimiter,
    paths: tuple[str, ...],
    now: Callable[[], float] = time.monotonic,
):
    """Limit only the paths that cost money.

    Health and config are deliberately exempt: throttling a load-balancer probe
    would take a healthy deployment out of rotation, and it costs nothing.
    """

    async def middleware(request: Request, call_next):
        if not request.url.path.startswith(paths):
            return await call_next(request)

        allowed, retry_after = limiter.check(client_key(request), now())
        if allowed:
            return await call_next(request)

        logger.warning("Rate limited %s on %s", client_key(request), request.url.path)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests — this endpoint spends LLM budget."},
            # The client's taxonomy already treats 429 as retryable; this tells
            # it how long to wait instead of guessing.
            headers={"Retry-After": str(max(1, round(retry_after)))},
        )

    return middleware
