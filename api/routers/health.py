from fastapi import APIRouter, Depends

from api.dependencies import get_service
from api.schemas import HealthResponse, MetricsResponse
from services.rag_service import RAGService

router = APIRouter(tags=["ops"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    description="Returns `{status: healthy}` as long as the process is running. "
    "Safe to call without a loaded pipeline — suitable for load-balancer probes.",
    response_description="Service health status",
)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@router.get(
    "/metrics",
    response_model=MetricsResponse,
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
async def metrics(service: RAGService = Depends(get_service)) -> MetricsResponse:
    return MetricsResponse(**service.get_metrics())
