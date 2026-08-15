"""Configuration and deep health.

`/config` exists so the UI never hardcodes what the pipeline is made of — a
settings page that lists "BAAI/bge-small-en-v1.5" from a TypeScript constant is
describing the frontend's belief, not the deployment.
"""

import os
import shutil

from fastapi import APIRouter, Depends

from api.dependencies import get_service
from api.schemas import ConfigResponse, DeepHealthResponse, HealthCheck
from config.logging_config import get_logger
from config.settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL,
    INDEX_DIR,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    MAX_CONTEXT_CHUNKS,
    MIN_CHUNK_CHARS,
    TOP_K,
)
from retrieval.ranking import RetrieverMode
from services.rag_service import RAGService

logger = get_logger(__name__)
router = APIRouter(tags=["ops"])

#: Free space below which retrieval still works but an index rebuild would not.
_DISK_WARNING_BYTES = 100 * 1024 * 1024


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Pipeline configuration and corpus size",
    description=(
        "What this deployment is actually running: models, chunking parameters, "
        "retrieval defaults and the size of the indexed corpus."
    ),
    responses={503: {"description": "Pipeline not available"}},
)
async def config(service: RAGService = Depends(get_service)) -> ConfigResponse:
    return ConfigResponse(
        embedding_model=EMBEDDING_MODEL,
        llm_model=LLM_MODEL,
        llm_temperature=LLM_TEMPERATURE,
        llm_max_tokens=LLM_MAX_TOKENS,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        min_chunk_chars=MIN_CHUNK_CHARS,
        default_top_k=TOP_K,
        max_context_chunks=MAX_CONTEXT_CHUNKS,
        retrievers=list(RetrieverMode.__args__),
        indexed_chunks=service.corpus_size(),
        documents=service.document_count(),
        reranker_enabled=False,
    )


@router.get(
    "/health/deep",
    response_model=DeepHealthResponse,
    summary="Dependency-by-dependency health",
    description=(
        "Unlike `/health`, this touches every dependency the pipeline needs. It is "
        "deliberately a separate endpoint: a load balancer probe must stay cheap and "
        "must not fail because a downstream API key is missing."
    ),
)
async def deep_health() -> DeepHealthResponse:
    checks = [_index_check(), _api_key_check(), _disk_check()]
    # Degraded rather than unhealthy when something is merely warned about: the
    # process is serving, and reporting it as down would take a deployment out
    # of rotation over free disk space.
    if any(c.status == "fail" for c in checks):
        status = "unhealthy"
    elif any(c.status == "warn" for c in checks):
        status = "degraded"
    else:
        status = "healthy"
    return DeepHealthResponse(status=status, checks=checks)


def _index_check() -> HealthCheck:
    missing = [p.name for p in (INDEX_DIR / "faiss.index", INDEX_DIR / "metadata.json") if not p.exists()]
    if missing:
        return HealthCheck(
            name="index",
            status="fail",
            detail=f"missing {', '.join(missing)} — run scripts/build_index.py",
        )
    return HealthCheck(name="index", status="pass", detail="FAISS index and metadata present")


def _api_key_check() -> HealthCheck:
    if not os.environ.get("GROQ_API_KEY"):
        # A warning, not a failure: retrieval and evaluation work without it.
        # Only generation does not.
        return HealthCheck(
            name="groq_api_key",
            status="warn",
            detail="GROQ_API_KEY unset — retrieval works, generation will 503",
        )
    return HealthCheck(name="groq_api_key", status="pass", detail="present")


def _disk_check() -> HealthCheck:
    free = shutil.disk_usage(INDEX_DIR.parent).free
    gb = free / 1024**3
    if free < _DISK_WARNING_BYTES:
        return HealthCheck(
            name="disk", status="warn", detail=f"{gb:.1f} GB free — too little to rebuild the index"
        )
    return HealthCheck(name="disk", status="pass", detail=f"{gb:.1f} GB free")
