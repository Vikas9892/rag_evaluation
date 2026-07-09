"""Server-Sent Events streaming endpoint.

Clients receive three event types:
  {"type": "sources", "data": [...]}   — retrieved chunks (sent first)
  {"type": "token",   "data": "..."}   — one answer token per event
  {"type": "done"}                     — stream complete; client may close
  {"type": "error",   "data": "..."}   — unrecoverable error
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.dependencies import get_service
from api.schemas import QueryRequest
from config.logging_config import get_logger
from services.rag_service import RAGService

logger = get_logger(__name__)
router = APIRouter(tags=["streaming"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post(
    "/stream",
    summary="Stream answer tokens via Server-Sent Events",
    description=(
        "Returns a `text/event-stream` response.  "
        "The first event contains retrieved source metadata; subsequent events "
        "carry individual LLM tokens; the final event signals completion."
    ),
    response_description="Server-Sent Event stream",
    responses={
        400: {"description": "Empty or whitespace-only question"},
        503: {"description": "Index or API key not available"},
    },
)
async def stream_endpoint(
    request: QueryRequest,
    service: RAGService = Depends(get_service),
) -> StreamingResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty or whitespace")

    def event_generator():
        try:
            for event in service.stream(request.question, top_k=request.top_k):
                yield f"data: {json.dumps(event)}\n\n"
        except NotImplementedError as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"
        except Exception as exc:
            logger.exception("Error in /stream")
            yield f"data: {json.dumps({'type': 'error', 'data': 'Internal server error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
