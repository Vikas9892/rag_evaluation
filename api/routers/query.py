from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_service
from api.schemas import QueryRequest, QueryResponse, SourceInfo
from config.logging_config import get_logger
from services.rag_service import RAGService

logger = get_logger(__name__)
router = APIRouter(tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Answer a question using the RAG pipeline",
    description=(
        "Embeds the question, retrieves the top-K most relevant chunks from the FAISS index, "
        "builds a grounded prompt, and calls the Groq LLM to generate an answer. "
        "The response includes per-source attribution and end-to-end latency metrics."
    ),
    response_description="Answer with sources and latency breakdown",
    responses={
        400: {"description": "Empty or whitespace-only question"},
        503: {"description": "FAISS index not built or GROQ_API_KEY missing"},
        504: {"description": "LLM request timed out after all retries"},
    },
)
async def query_endpoint(
    request: QueryRequest,
    service: RAGService = Depends(get_service),
) -> QueryResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty or whitespace")

    try:
        result = service.answer(request.question, top_k=request.top_k)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="LLM request timed out")
    except Exception:
        logger.exception("Unhandled error in POST /query")
        raise HTTPException(status_code=500, detail="Internal server error")

    sources = [
        SourceInfo(
            document_id=r.chunk.document_id,
            chunk_id=r.chunk.chunk_id,
            score=round(r.score, 4),
        )
        for r in result.sources
    ]

    return QueryResponse(
        answer=result.answer,
        sources=sources,
        retrieval_latency_ms=round(result.retrieval_latency_ms, 1),
        generation_latency_ms=round(result.generation_latency_ms, 1),
        total_latency_ms=round(
            result.retrieval_latency_ms + result.generation_latency_ms, 1
        ),
        request_id=result.request_id,
    )
