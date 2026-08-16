import math
import time
from dataclasses import dataclass
from typing import List

from config.logging_config import get_logger
from config.settings import TOP_K

from .dataset import BenchmarkSample
from .metrics import (
    hit_rate,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

logger = get_logger(__name__)


@dataclass
class RetrievalSampleResult:
    question_id: int
    question: str
    retrieved_ids: List[str]
    expected_ids: List[str]
    precision: float
    recall: float
    hit: bool
    reciprocal_rank: float
    latency_ms: float


@dataclass
class RetrievalAggregateResult:
    precision_at_k: float
    recall_at_k: float
    hit_rate: float
    mrr: float
    avg_latency_ms: float
    k: int
    #: Median and 95th percentile of the same per-question latencies the mean
    #: comes from. The mean alone hides the tail, and the tail is what a user
    #: waiting on a query actually experiences: one 900 ms outlier moves the
    #: mean by a few milliseconds and p95 by hundreds.
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0


class RetrievalEvaluator:
    """Measures retrieval quality against ground-truth chunk IDs.

    Completely independent of the LLM — if retrieval is broken, this
    catches it before any generation cost is incurred.
    """

    def __init__(self, retriever, top_k: int = TOP_K) -> None:
        self._retriever = retriever
        self.top_k = top_k

    def evaluate(
        self, dataset: List[BenchmarkSample]
    ) -> tuple[List[RetrievalSampleResult], RetrievalAggregateResult]:
        sample_results: List[RetrievalSampleResult] = []

        for sample in dataset:
            t0 = time.perf_counter()
            results = self._retriever.retrieve(sample.question, top_k=self.top_k)
            latency_ms = (time.perf_counter() - t0) * 1000

            retrieved_ids = [r.chunk.chunk_id for r in results]
            prec = precision_at_k(retrieved_ids, sample.expected_chunk_ids, self.top_k)
            rec = recall_at_k(retrieved_ids, sample.expected_chunk_ids)
            hit = bool(hit_rate(retrieved_ids, sample.expected_chunk_ids))
            rr = reciprocal_rank(retrieved_ids, sample.expected_chunk_ids)

            sample_results.append(
                RetrievalSampleResult(
                    question_id=sample.id,
                    question=sample.question,
                    retrieved_ids=retrieved_ids,
                    expected_ids=sample.expected_chunk_ids,
                    precision=prec,
                    recall=rec,
                    hit=hit,
                    reciprocal_rank=rr,
                    latency_ms=latency_ms,
                )
            )

        aggregate = self._aggregate(sample_results)
        logger.info(
            "Retrieval eval complete | P@%d=%.3f | R@%d=%.3f | MRR=%.3f",
            self.top_k,
            aggregate.precision_at_k,
            self.top_k,
            aggregate.recall_at_k,
            aggregate.mrr,
        )
        return sample_results, aggregate

    def _aggregate(
        self, results: List[RetrievalSampleResult]
    ) -> RetrievalAggregateResult:
        if not results:
            return RetrievalAggregateResult(0.0, 0.0, 0.0, 0.0, 0.0, self.top_k)
        n = len(results)
        latencies = [r.latency_ms for r in results]
        return RetrievalAggregateResult(
            precision_at_k=sum(r.precision for r in results) / n,
            recall_at_k=sum(r.recall for r in results) / n,
            hit_rate=sum(1 for r in results if r.hit) / n,
            mrr=mean_reciprocal_rank([r.reciprocal_rank for r in results]),
            avg_latency_ms=sum(latencies) / n,
            k=self.top_k,
            p50_latency_ms=percentile(latencies, 50),
            p95_latency_ms=percentile(latencies, 95),
        )


def percentile(values: List[float], q: float) -> float:
    """The q-th percentile by nearest rank.

    Nearest rank rather than interpolation: every value returned is a latency
    that was actually measured, so "p95 = 412 ms" names a real question that
    took that long. Interpolating would invent a number between two samples,
    which is defensible for a continuous distribution and misleading for a
    dataset of 53 discrete measurements.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    # ceil(q/100 * n), clamped — index 0 for the smallest, n-1 for the largest.
    rank = math.ceil(q / 100 * len(ordered))
    return ordered[min(max(rank, 1), len(ordered)) - 1]
