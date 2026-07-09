from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from api.routers import health, query
from api.routers import stream
from config.logging_config import get_logger

logger = get_logger(__name__)

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
    app.include_router(health.router)
    app.include_router(query.router)
    app.include_router(stream.router)
    return app


# Module-level instance for `uvicorn api.app:app`
app = create_app()
