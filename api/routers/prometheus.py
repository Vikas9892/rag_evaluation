"""Prometheus exposition.

`/metrics` already returns JSON that the dashboard reads, and Prometheus expects
a text format at that same conventional path. Rather than break the UI or serve
two formats by content negotiation — which makes "what does /metrics return?"
unanswerable without knowing the caller — the scrape endpoint gets its own path.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from api.dependencies import get_service
from services.rag_service import RAGService

router = APIRouter(tags=["ops"])

#: Exposition format: HELP, TYPE, then the sample.
_METRICS = (
    (
        "rag_queries_total",
        "counter",
        "Queries answered since cold start",
        "total_queries",
    ),
    ("rag_errors_total", "counter", "Queries that raised before returning", "errors"),
    (
        "rag_retrieval_latency_ms_avg",
        "gauge",
        "Mean retrieval latency in milliseconds",
        "avg_retrieval_ms",
    ),
    (
        "rag_generation_latency_ms_avg",
        "gauge",
        "Mean LLM generation latency in milliseconds",
        "avg_generation_ms",
    ),
)


@router.get(
    "/metrics/prometheus",
    response_class=PlainTextResponse,
    summary="Prometheus exposition of the in-process counters",
    description=(
        "The same counters as `GET /metrics`, in text exposition format. Values are "
        "per-process and reset on restart, which is what a counter from an "
        "in-memory source means — there is no persistence behind them."
    ),
    responses={503: {"description": "Pipeline not available"}},
)
async def prometheus(service: RAGService = Depends(get_service)) -> str:
    metrics = service.get_metrics()
    lines = []
    for name, kind, help_text, key in _METRICS:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        lines.append(f"{name} {metrics[key]}")
    # Exposition format requires a trailing newline.
    return "\n".join(lines) + "\n"
