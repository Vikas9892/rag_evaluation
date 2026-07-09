from functools import lru_cache

from fastapi import HTTPException

from config.logging_config import get_logger
from generation.generator import GroqGenerator
from generation.prompt_builder import PromptBuilder
from retrieval.retriever import Retriever
from services.rag_service import RAGService

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _build_service() -> RAGService:
    """Load all pipeline components exactly once per process lifetime."""
    logger.info("Loading RAG pipeline components...")
    retriever = Retriever.from_disk()
    builder = PromptBuilder()
    generator = GroqGenerator()
    service = RAGService(retriever=retriever, generator=generator, builder=builder)
    logger.info("RAG pipeline ready")
    return service


def get_service() -> RAGService:
    """FastAPI dependency that returns the process-scoped RAGService singleton."""
    try:
        return _build_service()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Index not available: {exc}")
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
