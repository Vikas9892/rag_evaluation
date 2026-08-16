"""Server-Sent Events streaming endpoint.

Clients receive four event types:
  {"type": "sources", "data": [...]}   — retrieved chunks (sent first)
  {"type": "token",   "data": "..."}   — one answer token per event
  {"type": "done",    "data": {...}}   — request_id and latency breakdown,
                                         including time-to-first-token
  {"type": "error",   "data": "..."}   — unrecoverable error

An error event can arrive *after* tokens have already been sent: the failure may
happen part-way through generation. Clients should keep what they have received
and report the failure alongside it rather than discarding a partial answer.
"""

import json

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.dependencies import get_service_resolver
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
    resolve_service: Callable[[str], RAGService] = Depends(get_service_resolver),
) -> StreamingResponse:
    service = resolve_service(request.corpus_id)
    if not request.question.strip():
        raise HTTPException(
            status_code=400, detail="Question cannot be empty or whitespace"
        )

    def event_generator():
        try:
            for event in service.stream(
                request.question,
                top_k=request.top_k,
                retriever=request.retriever,
                reranker=request.reranker,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except NotImplementedError as exc:
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"
        except Exception:
            # Deliberately unbound: the detail goes to the log, never to the
            # client, so an internal error cannot leak through the stream.
            logger.exception("Error in /stream")
            yield f"data: {json.dumps({'type': 'error', 'data': 'Internal server error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
