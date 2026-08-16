import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import start_indexing_worker, stop_indexing_worker
from api.rate_limit import TokenBucketLimiter, rate_limit_middleware
from api.routers import config as config_router
from api.routers import documents, evaluation, health, prometheus, query
from api.routers import stream
from config.logging_config import get_logger
from config.settings import DEFAULT_ALLOWED_ORIGINS

logger = get_logger(__name__)


def resolve_allowed_origins(raw: str | None = None) -> List[str]:
    """Parse the ALLOWED_ORIGINS env var into an origin allowlist.

    Blank entries are dropped so a trailing comma cannot smuggle in an empty
    origin.  Falls back to the local dev origin when unset.
    """
    value = raw if raw is not None else os.environ.get("ALLOWED_ORIGINS")
    if not value or not value.strip():
        return list(DEFAULT_ALLOWED_ORIGINS)

    origins = [o.strip() for o in value.split(",") if o.strip()]
    if "*" in origins:
        # Permitted as an operator override, but never silently: every browser
        # on the internet could then spend this deployment's Groq budget.
        logger.warning(
            "ALLOWED_ORIGINS contains '*' — the API is open to every origin. "
            "Set an explicit allowlist in any deployment that costs money."
        )
    return origins


# Generous enough that a person clicking around never notices, tight enough
# that a script pointed at /query cannot run up a bill unattended.
_RATE_PER_SECOND = float(os.environ.get("RATE_LIMIT_PER_SECOND", "1"))
_BURST = float(os.environ.get("RATE_LIMIT_BURST", "10"))

_TAGS_METADATA = [
    {
        "name": "query",
        "description": "RAG pipeline endpoint — retrieval + LLM generation.",
    },
    {
        "name": "streaming",
        "description": "Server-Sent Events variant of /query for token-level streaming.",
    },
    {
        "name": "ops",
        "description": "Liveness and metrics — suitable for load-balancer probes.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RAG API starting up")
    # The worker starts with the app and stops with it, so a queued job is
    # picked up without anyone running a second process.
    start_indexing_worker()
    yield
    stop_indexing_worker()
    logger.info("RAG API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG Evaluation API",
        description=(
            "Production RAG pipeline with semantic retrieval (FAISS + BGE) and "
            "LLM generation (Groq / llama-3.1-8b-instant).\n\n"
            "**Endpoints**\n"
            "- `POST /query` — blocking request/response\n"
            "- `POST /stream` — token-level SSE streaming\n"
            "- `GET /health` — liveness probe\n"
            "- `GET /metrics` — per-container performance counters\n\n"
            "**Auth**: set `GROQ_API_KEY` as an environment variable before starting."
        ),
        version="1.0.0",
        openapi_tags=_TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    origins = resolve_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # No cookies or Authorization header are used, so credentials stay off.
        # Leaving it on would also forbid a wildcard origin outright.
        allow_credentials=False,
        # Only what the client actually issues — /query and /stream are POST,
        # /health and /metrics are GET, and a document is removed with DELETE.
        # This list going stale is invisible in unit tests, which never make a
        # cross-origin request: DELETE was missing here for as long as document
        # deletion existed, and the browser failed the preflight every time.
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    logger.info("CORS allowlist: %s", ", ".join(origins))

    # Only the endpoints that spend Groq budget. A throttled health probe
    # would take a healthy deployment out of rotation for free.
    app.middleware("http")(
        rate_limit_middleware(
            TokenBucketLimiter(rate=_RATE_PER_SECOND, capacity=_BURST),
            paths=("/query", "/stream"),
        )
    )

    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(stream.router)
    app.include_router(config_router.router)
    app.include_router(evaluation.router)
    app.include_router(prometheus.router)
    app.include_router(documents.router)
    return app


# Module-level instance for `uvicorn api.app:app`
app = create_app()
