import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List

from config.logging_config import get_logger
from config.settings import TOP_K

from .dataset import BenchmarkSample
from .generation_evaluator import GenerationAggregateResult, GenerationEvaluator, GenerationSampleResult
from .retrieval_evaluator import RetrievalAggregateResult, RetrievalEvaluator, RetrievalSampleResult

logger = get_logger(__name__)


@dataclass
class BenchmarkResult:
    retrieval: RetrievalAggregateResult
    generation: GenerationAggregateResult
    retrieval_samples: List[RetrievalSampleResult]
    generation_samples: List[GenerationSampleResult]
    timestamp: str
    config: Dict = field(default_factory=dict)

    def as_flat_dict(self) -> dict:
        """Single-row summary suitable for CSV or Markdown."""
        d = {
            "timestamp": self.timestamp,
            "questions": len(self.retrieval_samples),
            f"precision_at_{self.retrieval.k}": round(self.retrieval.precision_at_k, 4),
            f"recall_at_{self.retrieval.k}": round(self.retrieval.recall_at_k, 4),
            "hit_rate": round(self.retrieval.hit_rate, 4),
            "mrr": round(self.retrieval.mrr, 4),
            "avg_retrieval_ms": round(self.retrieval.avg_latency_ms, 1),
            "avg_semantic_similarity": round(self.generation.avg_semantic_similarity, 4),
            "faithfulness_rate": (
                round(self.generation.faithfulness_rate, 4)
                if self.generation.faithfulness_rate is not None
                else "N/A"
            ),
            "avg_generation_ms": round(self.generation.avg_latency_ms, 1),
        }
        d.update(self.config)
        return d


class BenchmarkRunner:
    """Orchestrates the full evaluation loop over a benchmark dataset.

    Separates retrieval and generation evaluation so each can be diagnosed
    independently — a dropped Precision@K doesn't necessarily mean the LLM
    is the problem.
    """

    def __init__(
        self,
        retriever,
        generator,
        embedder,
        builder,
        dataset: List[BenchmarkSample],
        top_k: int = TOP_K,
        faithfulness_generator=None,
    ) -> None:
        self._retrieval_eval = RetrievalEvaluator(retriever, top_k=top_k)
        self._generation_eval = GenerationEvaluator(
            generator, builder, embedder, faithfulness_generator
        )
        self._dataset = dataset
        self._top_k = top_k

    def run(self) -> BenchmarkResult:
        logger.info("Starting benchmark over %d question(s)", len(self._dataset))
        t0 = time.perf_counter()

        # --- Retrieval pass ---
        retrieval_samples, retrieval_agg = self._retrieval_eval.evaluate(self._dataset)

        # Build a lookup: question_id -> retrieved results (needed by generation eval)
        # We re-run retrieval here only to pass RetrievalResult objects to generation.
        # The latency was already measured in the retrieval eval; this second call is
        # fast since we're just re-fetching the same vectors.
        retrieval_map: Dict[int, list] = {}
        for sample in self._dataset:
            retrieval_map[sample.id] = self._retrieval_eval._retriever.retrieve(
                sample.question, top_k=self._top_k
            )

        # --- Generation pass ---
        generation_samples, generation_agg = self._generation_eval.evaluate(
            self._dataset, retrieval_map
        )

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info("Benchmark complete in %.0f ms", elapsed)

        return BenchmarkResult(
            retrieval=retrieval_agg,
            generation=generation_agg,
            retrieval_samples=retrieval_samples,
            generation_samples=generation_samples,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            config={"top_k": self._top_k},
        )


class ExperimentRunner:
    """Sweeps a list of pipeline configurations and compares retrieval metrics.

    Each config is a dict passed to the pipeline_factory.  Generation is
    intentionally excluded from the sweep to avoid repeated API costs.

    Example configs:
        [
            {"chunk_size": 256, "chunk_overlap": 50,  "top_k": 3},
            {"chunk_size": 512, "chunk_overlap": 100, "top_k": 5},
            {"chunk_size": 1024,"chunk_overlap": 200, "top_k": 5},
        ]
    """

    def __init__(
        self,
        configs: List[dict],
        pipeline_factory: Callable[[dict], tuple],
        dataset: List[BenchmarkSample],
    ) -> None:
        self._configs = configs
        self._factory = pipeline_factory
        self._dataset = dataset

    def run(self) -> List[dict]:
        rows: List[dict] = []
        for cfg in self._configs:
            logger.info("Running experiment config: %s", cfg)
            retriever, top_k = self._factory(cfg)
            evaluator = RetrievalEvaluator(retriever, top_k=top_k)
            _, agg = evaluator.evaluate(self._dataset)
            row = {
                **cfg,
                f"precision_at_{top_k}": round(agg.precision_at_k, 4),
                f"recall_at_{top_k}": round(agg.recall_at_k, 4),
                "hit_rate": round(agg.hit_rate, 4),
                "mrr": round(agg.mrr, 4),
                "avg_latency_ms": round(agg.avg_latency_ms, 1),
            }
            rows.append(row)
        return rows
