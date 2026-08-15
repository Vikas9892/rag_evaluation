"""Tests for the token-bucket rate limiter.

The limiter exists to cap spend, not to authenticate: /query and /stream each
cost a Groq call, and CORS only stops other people's *pages* from making them.
Time is injected so these assert the refill maths rather than sleeping.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.rate_limit import TokenBucketLimiter, client_key, rate_limit_middleware


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestTokenBucket:
    def test_allows_up_to_the_burst(self):
        limiter = TokenBucketLimiter(rate=1, capacity=3)
        assert [limiter.check("a", 0.0)[0] for _ in range(3)] == [True, True, True]

    def test_refuses_once_the_burst_is_spent(self):
        limiter = TokenBucketLimiter(rate=1, capacity=2)
        limiter.check("a", 0.0)
        limiter.check("a", 0.0)
        allowed, retry_after = limiter.check("a", 0.0)

        assert allowed is False
        assert retry_after == pytest.approx(1.0)

    def test_refills_continuously_rather_than_on_a_window_boundary(self):
        # A window reset would let a client spend the whole budget at 11:59:59
        # and again one second later.
        limiter = TokenBucketLimiter(rate=2, capacity=2)
        limiter.check("a", 0.0)
        limiter.check("a", 0.0)

        assert limiter.check("a", 0.25)[0] is False
        assert limiter.check("a", 0.5)[0] is True

    def test_does_not_refill_beyond_the_burst(self):
        # An idle client cannot bank an unlimited allowance.
        limiter = TokenBucketLimiter(rate=1, capacity=2)
        limiter.check("a", 0.0)
        assert [limiter.check("a", 3600.0)[0] for _ in range(3)] == [True, True, False]

    def test_clients_are_limited_independently(self):
        limiter = TokenBucketLimiter(rate=1, capacity=1)
        limiter.check("a", 0.0)

        assert limiter.check("a", 0.0)[0] is False
        assert limiter.check("b", 0.0)[0] is True


def build_app(clock: FakeClock, rate: float = 1, capacity: float = 2) -> FastAPI:
    app = FastAPI()
    app.middleware("http")(
        rate_limit_middleware(
            TokenBucketLimiter(rate=rate, capacity=capacity),
            paths=("/query", "/stream"),
            now=clock,
        )
    )

    @app.post("/query")
    async def query():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


class TestMiddleware:
    def test_lets_requests_through_within_the_burst(self):
        client = TestClient(build_app(FakeClock()))
        assert [client.post("/query").status_code for _ in range(2)] == [200, 200]

    def test_answers_429_once_exhausted(self):
        client = TestClient(build_app(FakeClock()))
        client.post("/query")
        client.post("/query")

        assert client.post("/query").status_code == 429

    def test_says_how_long_to_wait(self):
        # The client's taxonomy already retries a 429; this stops it guessing.
        client = TestClient(build_app(FakeClock()))
        client.post("/query")
        client.post("/query")
        response = client.post("/query")

        assert int(response.headers["retry-after"]) >= 1

    def test_recovers_once_the_bucket_refills(self):
        clock = FakeClock()
        client = TestClient(build_app(clock))
        client.post("/query")
        client.post("/query")
        assert client.post("/query").status_code == 429

        clock.advance(1.0)
        assert client.post("/query").status_code == 200

    def test_does_not_throttle_the_health_probe(self):
        # Throttling a load-balancer probe would take a healthy deployment out
        # of rotation, and it costs nothing to serve.
        client = TestClient(build_app(FakeClock()))
        for _ in range(5):
            client.post("/query")

        assert client.get("/health").status_code == 200


class TestClientKey:
    def test_prefers_the_forwarded_address(self):
        # Behind a proxy every request shares the proxy's address, so one client
        # would exhaust everyone's budget.
        class Req:
            headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}
            client = type("C", (), {"host": "10.0.0.1"})()

        assert client_key(Req()) == "203.0.113.9"

    def test_falls_back_to_the_socket_address(self):
        class Req:
            headers = {}
            client = type("C", (), {"host": "198.51.100.4"})()

        assert client_key(Req()) == "198.51.100.4"
