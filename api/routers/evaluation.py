"""Evaluation and benchmark endpoints.

These are the accuracy surface. The product spec keeps them apart from the query
surface for a reason: Precision@K, Recall and MRR are undefined without ground
truth, and an ad-hoc question has none. Everything here runs against the
labelled dataset and nothing here answers a user's question.

Retrieval evaluation costs no LLM calls, so it runs on request. Generation
evaluation does, so it is opt-in.
"""

import os
import time
from threading import Lock
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_service
from api.schemas import (
    BenchmarkCell,
    BenchmarkResponse,
    EvaluationResponse,
    PerQuestionResult,
    RetrievalMetrics,
)
from config.logging_config import get_logger
from config.settings import TOP_K
from evaluation.dataset import DatasetLoader
from evaluation.ground_truth import ChunkResolver
from evaluation.retrieval_evaluator import RetrievalEvaluator
from retrieval.ranking import RetrieverMode
from services.rag_service import RAGService

logger = get_logger(__name__)
router = APIRouter(tags=["evaluation"])

#: Configurations the benchmark matrix sweeps.
_BENCHMARK_TOP_K = (3, 5, 10)
_BENCHMARK_RETRIEVERS: Tuple[RetrieverMode, ...] = ("dense", "sparse", "hybrid")
# Whether the cross-encoder earns its latency is exactly the sort of question
# this platform exists to answer, so it is swept rather than assumed.
_BENCHMARK_RERANKER: Tuple[bool, ...] = (False, True)

# How long one /benchmarks call may spend computing uncached cells.
#
# The full sweep takes minutes — reranking scores every candidate for every
# question in the dataset — and a request that long does not survive contact
# with a proxy, a load balancer or an impatient client. It killed the dev server
# outright when a client hung up mid-run. So each call does a bounded amount of
# work, returns what it has, and names what is still pending; the client asks
# again to continue. Progress accumulates in the cache, so the matrix fills in
# across a few requests instead of failing on one.
_BENCHMARK_BUDGET_SECONDS = float(os.environ.get("BENCHMARK_BUDGET_SECONDS", "20"))

# An evaluation run embeds every question in the dataset, so the same request
# twice would pay the same ~2 s twice. Results are pure functions of (dataset,
# index, config), none of which change while the process is up, so caching them
# in memory is sound. Redis was the plan; it would add a service to operate for
# a cache that a single process can hold, and the moment this runs on more than
# one process the index would have to be shared too.
_cache: Dict[tuple, object] = {}
_cache_lock = Lock()


def _cached(key: tuple, produce):
    with _cache_lock:
        if key in _cache:
            return _cache[key], True
    value = produce()
    with _cache_lock:
        _cache[key] = value
    return value, False


def _load_dataset():
    try:
        return DatasetLoader.load(resolver=ChunkResolver.from_disk())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Index not available: {exc}")


def _evaluate(
    service: RAGService, top_k: int, retriever: RetrieverMode, reranker: bool = False
):
    """Retrieval metrics for one configuration."""

    dataset = _load_dataset()

    class _Bound:
        """Pins the configuration, which RetrievalEvaluator does not know about."""

        def __init__(self, inner):
            self._inner = inner

        def retrieve(self, question: str, top_k: int):
            return self._inner.retrieve(
                question, top_k=top_k, mode=retriever, reranker=reranker
            )

    evaluator = RetrievalEvaluator(_Bound(service.retriever), top_k=top_k)
    return evaluator.evaluate(dataset)


def _metrics_from(aggregate) -> RetrievalMetrics:
    """One construction site, so a new metric cannot reach /evaluation and
    silently miss /benchmarks."""
    return RetrievalMetrics(
        precision_at_k=round(aggregate.precision_at_k, 4),
        recall_at_k=round(aggregate.recall_at_k, 4),
        hit_rate=round(aggregate.hit_rate, 4),
        mrr=round(aggregate.mrr, 4),
        avg_latency_ms=round(aggregate.avg_latency_ms, 1),
        p50_latency_ms=round(aggregate.p50_latency_ms, 1),
        p95_latency_ms=round(aggregate.p95_latency_ms, 1),
    )


@router.get(
    "/evaluation",
    response_model=EvaluationResponse,
    summary="Retrieval quality over the labelled dataset",
    description=(
        "Precision@K, Recall, Hit Rate and MRR measured against ground-truth chunk "
        "spans, plus the per-question breakdown. No LLM calls are made."
    ),
    responses={503: {"description": "Index or dataset not available"}},
)
async def evaluation(
    top_k: int = Query(default=TOP_K, ge=1, le=20),
    retriever: RetrieverMode = Query(default="hybrid"),
    reranker: bool = Query(default=False),
    service: RAGService = Depends(get_service),
) -> EvaluationResponse:
    t0 = time.perf_counter()
    (samples, aggregate), cached = _cached(
        ("eval", top_k, retriever, reranker),
        lambda: _evaluate(service, top_k, retriever, reranker),
    )
    elapsed = (time.perf_counter() - t0) * 1000

    logger.info(
        "Evaluation top_k=%d retriever=%s -> MRR %.3f (%s)",
        top_k,
        retriever,
        aggregate.mrr,
        "cached" if cached else f"{elapsed:.0f} ms",
    )

    return EvaluationResponse(
        top_k=top_k,
        retriever=retriever,
        reranker=reranker,
        dataset_size=len(samples),
        cached=cached,
        metrics=_metrics_from(aggregate),
        questions=[
            PerQuestionResult(
                id=s.question_id,
                question=s.question,
                hit=s.hit,
                precision=round(s.precision, 4),
                recall=round(s.recall, 4),
                reciprocal_rank=round(s.reciprocal_rank, 4),
                latency_ms=round(s.latency_ms, 1),
                retrieved_ids=s.retrieved_ids,
                expected_ids=s.expected_ids,
            )
            for s in samples
        ],
    )


@router.get(
    "/benchmarks",
    response_model=BenchmarkResponse,
    summary="Retrieval quality across configurations",
    description=(
        "Sweeps retriever × top-K and reports each cell's metrics, so configurations "
        "can be compared rather than argued about."
    ),
    responses={503: {"description": "Index or dataset not available"}},
)
async def benchmarks(service: RAGService = Depends(get_service)) -> BenchmarkResponse:
    cells: List[BenchmarkCell] = []
    pending = 0
    deadline = time.monotonic() + _BENCHMARK_BUDGET_SECONDS

    for retriever in _BENCHMARK_RETRIEVERS:
        for k in _BENCHMARK_TOP_K:
            for rerank in _BENCHMARK_RERANKER:
                key = ("eval", k, retriever, rerank)
                with _cache_lock:
                    already = key in _cache

                # Past the budget, an uncached cell is left for the next call
                # rather than making this one run long enough to be dropped.
                if not already and time.monotonic() >= deadline:
                    pending += 1
                    continue

                (samples, aggregate), _ = _cached(
                    key,
                    lambda r=retriever, kk=k, rr=rerank: _evaluate(service, kk, r, rr),
                )
                cells.append(
                    BenchmarkCell(
                        retriever=retriever,
                        top_k=k,
                        reranker=rerank,
                        metrics=_metrics_from(aggregate),
                    )
                )

    dataset_size = len(_load_dataset())
    distinct_mrr = {round(c.metrics.mrr, 4) for c in cells}

    return BenchmarkResponse(
        dataset_size=dataset_size,
        cells=cells,
        pending=pending,
        cached=pending == 0,
        # Surfaced rather than left for the reader to notice: when every
        # configuration scores the same, the matrix is measuring the corpus and
        # not the retriever, and presenting it as a comparison would be a claim
        # the data does not support.
        # Only meaningful once every cell is in. A partial matrix where the
        # first two cells happen to tie is not evidence that nothing separates
        # the configurations.
        discriminating=pending == 0 and len(distinct_mrr) > 1,
    )
