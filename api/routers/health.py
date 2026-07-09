from fastapi import APIRouter, Depends

from api.dependencies import get_service
from services.rag_service import RAGService

router = APIRouter(tags=["ops"])


@router.get(
    "/health",
    summary="Liveness check",
    description="Returns `{status: healthy}` as long as the process is running. "
    "Safe to call without a loaded pipeline — suitable for load-balancer probes.",
    response_description="Service health status",
)
async def health() -> dict:
    return {"status": "healthy"}


@router.get(
    "/metrics",
    summary="In-process performance metrics",
    description=(
        "Returns per-container counters accumulated since cold start: "
        "total query count, average retrieval latency, average generation latency, "
        "and error count.  These are single-container metrics — use CloudWatch "
        "for fleet-wide aggregation."
    ),
    response_description="Aggregated query metrics",
    responses={503: {"description": "Pipeline not available"}},
)
async def metrics(service: RAGService = Depends(get_service)) -> dict:
    return service.get_metrics()
