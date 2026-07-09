from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routers import health, query
from config.logging_config import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RAG API starting up")
    yield
    logger.info("RAG API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG Evaluation API",
        description="Production RAG pipeline — semantic retrieval + LLM generation",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(query.router)
    return app


# Module-level instance for `uvicorn api.app:app`
app = create_app()
