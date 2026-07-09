from dataclasses import dataclass
from typing import List

from config.logging_config import get_logger
from generation.models import Prompt
from retrieval.ranking import RetrievalResult

from .dataset import BenchmarkSample
from .metrics import cosine_similarity

logger = get_logger(__name__)

_FAITHFULNESS_SYSTEM = (
    "You are a strict faithful-answer evaluator. "
    "Determine whether the generated answer uses ONLY information from the context. "
    "Respond with exactly one word: FAITHFUL or UNFAITHFUL."
)


@dataclass
class GenerationSampleResult:
    question_id: int
    question: str
    generated_answer: str
    expected_answer: str
    semantic_similarity: float
    faithful: bool | None
    answer_words: int
    latency_ms: float


@dataclass
class GenerationAggregateResult:
    avg_semantic_similarity: float
    faithfulness_rate: float | None
    avg_answer_words: float
    avg_latency_ms: float


class GenerationEvaluator:
    """Measures answer quality against expected answers.

    semantic_similarity — cosine similarity between embedded answers;
                          catches paraphrases that exact-match would miss.
    faithfulness        — LLM-as-judge: does the answer stay grounded in
                          the retrieved context?  Skipped when no judge is
                          injected (faithfulness_generator=None).
    """

    def __init__(
        self,
        generator,
        builder,
        embedder,
        faithfulness_generator=None,
    ) -> None:
        self._generator = generator
        self._builder = builder
        self._embedder = embedder
        self._faithfulness_generator = faithfulness_generator

    # ------------------------------------------------------------------
    # Per-sample
    # ------------------------------------------------------------------

    def evaluate_sample(
        self,
        sample: BenchmarkSample,
        retrieved_results: List[RetrievalResult],
    ) -> GenerationSampleResult:
        prompt = self._builder.build(sample.question, retrieved_results)
        response = self._generator.generate(prompt, retrieved_results)

        sem_sim = self._semantic_similarity(response.answer, sample.expected_answer)

        faithful: bool | None = None
        if self._faithfulness_generator is not None:
            faithful = self._check_faithfulness(response.answer, retrieved_results)

        return GenerationSampleResult(
            question_id=sample.id,
            question=sample.question,
            generated_answer=response.answer,
            expected_answer=sample.expected_answer,
            semantic_similarity=sem_sim,
            faithful=faithful,
            answer_words=len(response.answer.split()),
            latency_ms=response.latency_ms,
        )

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def evaluate(
        self,
        dataset: List[BenchmarkSample],
        retrieval_map: dict[int, List[RetrievalResult]],
    ) -> tuple[List[GenerationSampleResult], GenerationAggregateResult]:
        sample_results: List[GenerationSampleResult] = []

        for sample in dataset:
            retrieved = retrieval_map.get(sample.id, [])
            result = self.evaluate_sample(sample, retrieved)
            sample_results.append(result)

        aggregate = self._aggregate(sample_results)
        logger.info(
            "Generation eval complete | SemanticSim=%.3f | Faithfulness=%s",
            aggregate.avg_semantic_similarity,
            f"{aggregate.faithfulness_rate:.3f}" if aggregate.faithfulness_rate is not None else "N/A",
        )
        return sample_results, aggregate

    def _aggregate(
        self, results: List[GenerationSampleResult]
    ) -> GenerationAggregateResult:
        if not results:
            return GenerationAggregateResult(0.0, None, 0.0, 0.0)
        n = len(results)
        faith_results = [r.faithful for r in results if r.faithful is not None]
        return GenerationAggregateResult(
            avg_semantic_similarity=sum(r.semantic_similarity for r in results) / n,
            faithfulness_rate=(
                sum(faith_results) / len(faith_results) if faith_results else None
            ),
            avg_answer_words=sum(r.answer_words for r in results) / n,
            avg_latency_ms=sum(r.latency_ms for r in results) / n,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _semantic_similarity(self, answer_a: str, answer_b: str) -> float:
        v_a = self._embedder.embed(answer_a)
        v_b = self._embedder.embed(answer_b)
        return cosine_similarity(v_a, v_b)

    def _check_faithfulness(
        self, generated_answer: str, retrieved_results: List[RetrievalResult]
    ) -> bool:
        context = "\n\n".join(r.chunk.text for r in retrieved_results)
        user = (
            f"Context:\n{context}\n\n"
            f"Generated Answer:\n{generated_answer}\n\n"
            "Is this answer faithful? Respond with FAITHFUL or UNFAITHFUL."
        )
        response = self._faithfulness_generator.generate(
            Prompt(system=_FAITHFULNESS_SYSTEM, user=user), []
        )
        upper = response.answer.upper()
        return "UNFAITHFUL" not in upper and "FAITHFUL" in upper
