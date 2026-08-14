import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from api.routers import health, query
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
    yield
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
        # /health and /metrics are GET.
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    logger.info("CORS allowlist: %s", ", ".join(origins))

    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(stream.router)
    return app


# Module-level instance for `uvicorn api.app:app`
app = create_app()
