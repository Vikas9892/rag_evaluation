import time
from dataclasses import dataclass
from typing import List

from config.logging_config import get_logger
from config.settings import TOP_K

from .dataset import BenchmarkSample
from .metrics import hit_rate, mean_reciprocal_rank, precision_at_k, recall_at_k, reciprocal_rank

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
            self.top_k, aggregate.precision_at_k,
            self.top_k, aggregate.recall_at_k,
            aggregate.mrr,
        )
        return sample_results, aggregate

    def _aggregate(
        self, results: List[RetrievalSampleResult]
    ) -> RetrievalAggregateResult:
        if not results:
            return RetrievalAggregateResult(0.0, 0.0, 0.0, 0.0, 0.0, self.top_k)
        n = len(results)
        return RetrievalAggregateResult(
            precision_at_k=sum(r.precision for r in results) / n,
            recall_at_k=sum(r.recall for r in results) / n,
            hit_rate=sum(1 for r in results if r.hit) / n,
            mrr=mean_reciprocal_rank([r.reciprocal_rank for r in results]),
            avg_latency_ms=sum(r.latency_ms for r in results) / n,
            k=self.top_k,
        )
