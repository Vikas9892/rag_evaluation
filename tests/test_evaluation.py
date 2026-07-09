"""Unit tests for Phase 6 — evaluation pipeline."""
import json
import sys
from pathlib import Path
from typing import List

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chunking.chunk import Chunk
from generation.generator import BaseGenerator
from generation.models import GenerationResponse, Prompt
from retrieval.ranking import RetrievalResult

from evaluation.dataset import BenchmarkSample, DatasetLoader
from evaluation.metrics import (
    cosine_similarity,
    hit_rate,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from evaluation.retrieval_evaluator import RetrievalEvaluator
from evaluation.generation_evaluator import GenerationEvaluator
from evaluation.benchmark import BenchmarkResult, BenchmarkRunner
from evaluation.report import ReportGenerator


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class MockRetriever:
    """Returns a fixed list of RetrievalResult for every query."""

    def __init__(self, results: List[RetrievalResult]) -> None:
        self._results = results

    def retrieve(self, query: str, top_k: int = 5) -> List[RetrievalResult]:  # noqa: ARG002
        return self._results[:top_k]


class MockEmbedder:
    dimension = 4

    def __init__(self, vector: np.ndarray | None = None) -> None:
        self._vector = vector if vector is not None else np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    def embed(self, text: str) -> np.ndarray:  # noqa: ARG002
        return self._vector


class MockGenerator(BaseGenerator):
    def __init__(self, answer: str = "Mock answer.") -> None:
        self._answer = answer

    def generate(self, prompt: Prompt, sources: List[RetrievalResult]) -> GenerationResponse:
        return GenerationResponse(
            answer=self._answer,
            sources=sources,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=20.0,
        )


def make_chunk(chunk_id: str = "doc_chunk_0000", doc_id: str = "doc.txt") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        text=f"This is the text for {chunk_id}.",
        start_char=0,
        end_char=30,
        metadata={"source": doc_id, "chunk_index": 0},
    )


def make_result(chunk_id: str, rank: int = 1) -> RetrievalResult:
    return RetrievalResult(
        chunk=make_chunk(chunk_id),
        score=round(1.0 - rank * 0.1, 2),
        rank=rank,
    )


def make_sample(
    question_id: int = 1,
    question: str = "What is X?",
    expected_answer: str = "X is Y.",
    expected_chunk_ids: List[str] | None = None,
) -> BenchmarkSample:
    return BenchmarkSample(
        id=question_id,
        question=question,
        expected_answer=expected_answer,
        expected_chunk_ids=expected_chunk_ids or ["doc_chunk_0000"],
    )


# ---------------------------------------------------------------------------
# BenchmarkSample
# ---------------------------------------------------------------------------

class TestBenchmarkSample:
    def test_fields_are_set(self):
        s = make_sample(1, "Q?", "A.", ["c1", "c2"])
        assert s.id == 1
        assert s.question == "Q?"
        assert s.expected_answer == "A."
        assert s.expected_chunk_ids == ["c1", "c2"]

    def test_equality(self):
        assert make_sample(1) == make_sample(1)

    def test_inequality_on_id(self):
        assert make_sample(1) != make_sample(2)


# ---------------------------------------------------------------------------
# DatasetLoader
# ---------------------------------------------------------------------------

class TestDatasetLoader:
    def test_loads_json_file(self, tmp_path):
        data = [
            {
                "id": 1,
                "question": "Q?",
                "expected_answer": "A.",
                "expected_chunk_ids": ["c1"],
            }
        ]
        p = tmp_path / "dataset.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        samples = DatasetLoader.load(p)
        assert len(samples) == 1
        assert samples[0].question == "Q?"

    def test_returns_list_of_benchmark_samples(self, tmp_path):
        data = [{"id": i, "question": f"Q{i}?", "expected_answer": "A.", "expected_chunk_ids": []} for i in range(3)]
        p = tmp_path / "ds.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        samples = DatasetLoader.load(p)
        assert all(isinstance(s, BenchmarkSample) for s in samples)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            DatasetLoader.load(tmp_path / "ghost.json")

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_text("[]", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            DatasetLoader.load(p)

    def test_real_dataset_loads(self):
        samples = DatasetLoader.load()
        assert len(samples) == 15
        assert all(s.expected_chunk_ids for s in samples)


# ---------------------------------------------------------------------------
# Metrics — precision
# ---------------------------------------------------------------------------

class TestPrecisionAtK:
    def test_all_relevant(self):
        assert precision_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == pytest.approx(1.0)

    def test_none_relevant(self):
        assert precision_at_k(["x", "y"], ["a", "b"], k=2) == pytest.approx(0.0)

    def test_partial(self):
        assert precision_at_k(["a", "x", "b", "y"], ["a", "b"], k=4) == pytest.approx(0.5)

    def test_k_clips_list(self):
        # Only first k items considered
        assert precision_at_k(["x", "x", "a"], ["a"], k=2) == pytest.approx(0.0)

    def test_k_zero_returns_zero(self):
        assert precision_at_k(["a"], ["a"], k=0) == 0.0

    def test_empty_retrieved(self):
        assert precision_at_k([], ["a"], k=3) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Metrics — recall
# ---------------------------------------------------------------------------

class TestRecallAtK:
    def test_full_recall(self):
        assert recall_at_k(["a", "b", "c"], ["a", "b"]) == pytest.approx(1.0)

    def test_partial_recall(self):
        assert recall_at_k(["a", "x"], ["a", "b"]) == pytest.approx(0.5)

    def test_zero_recall(self):
        assert recall_at_k(["x", "y"], ["a", "b"]) == pytest.approx(0.0)

    def test_empty_relevant_returns_one(self):
        assert recall_at_k(["a", "b"], []) == pytest.approx(1.0)

    def test_empty_retrieved(self):
        assert recall_at_k([], ["a"]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Metrics — hit rate
# ---------------------------------------------------------------------------

class TestHitRate:
    def test_hit(self):
        assert hit_rate(["x", "a", "y"], ["a"]) == pytest.approx(1.0)

    def test_miss(self):
        assert hit_rate(["x", "y"], ["a", "b"]) == pytest.approx(0.0)

    def test_empty_retrieved(self):
        assert hit_rate([], ["a"]) == pytest.approx(0.0)

    def test_empty_relevant(self):
        assert hit_rate(["a"], []) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Metrics — reciprocal rank
# ---------------------------------------------------------------------------

class TestReciprocalRank:
    def test_rank_1(self):
        assert reciprocal_rank(["a", "b"], ["a"]) == pytest.approx(1.0)

    def test_rank_2(self):
        assert reciprocal_rank(["x", "a", "b"], ["a"]) == pytest.approx(0.5)

    def test_rank_5(self):
        assert reciprocal_rank(["x", "x", "x", "x", "a"], ["a"]) == pytest.approx(0.2)

    def test_not_found(self):
        assert reciprocal_rank(["x", "y"], ["a"]) == pytest.approx(0.0)

    def test_multiple_relevant_returns_first(self):
        # First hit at rank 2, second at rank 4 — we report rank 2
        assert reciprocal_rank(["x", "a", "y", "b"], ["a", "b"]) == pytest.approx(0.5)


class TestMeanReciprocalRank:
    def test_single(self):
        assert mean_reciprocal_rank([1.0]) == pytest.approx(1.0)

    def test_average(self):
        assert mean_reciprocal_rank([1.0, 0.5]) == pytest.approx(0.75)

    def test_empty(self):
        assert mean_reciprocal_rank([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Metrics — cosine similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        v = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_opposite_vectors_return_minus_one(self):
        v = np.array([1.0, 0.0, 0.0])
        assert cosine_similarity(v, -v) == pytest.approx(-1.0)

    def test_orthogonal_vectors_return_zero(self):
        assert cosine_similarity(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(0.0)

    def test_zero_vector_returns_zero(self):
        assert cosine_similarity(np.zeros(3), np.array([1.0, 2.0, 3.0])) == 0.0

    def test_result_in_valid_range(self):
        rng = np.random.default_rng(42)
        for _ in range(20):
            a = rng.random(8).astype(np.float32)
            b = rng.random(8).astype(np.float32)
            sim = cosine_similarity(a, b)
            assert -1.0 <= sim <= 1.0


# ---------------------------------------------------------------------------
# RetrievalEvaluator
# ---------------------------------------------------------------------------

class TestRetrievalEvaluator:
    def _evaluator(self, retrieved_ids: List[str]) -> RetrievalEvaluator:
        results = [make_result(cid, rank=i + 1) for i, cid in enumerate(retrieved_ids)]
        return RetrievalEvaluator(MockRetriever(results), top_k=5)

    def test_returns_sample_results_and_aggregate(self):
        ev = self._evaluator(["doc_chunk_0000", "doc_chunk_0001"])
        samples, agg = ev.evaluate([make_sample(expected_chunk_ids=["doc_chunk_0000"])])
        assert len(samples) == 1
        assert 0.0 <= agg.precision_at_k <= 1.0

    def test_perfect_retrieval_precision_one(self):
        ids = [f"chunk_{i:04d}" for i in range(5)]
        ev = RetrievalEvaluator(MockRetriever([make_result(i) for i in ids]), top_k=5)
        samples, agg = ev.evaluate(
            [make_sample(expected_chunk_ids=ids)]
        )
        assert agg.precision_at_k == pytest.approx(1.0)

    def test_miss_gives_zero_hit_rate(self):
        ev = self._evaluator(["wrong_chunk"])
        _, agg = ev.evaluate([make_sample(expected_chunk_ids=["correct_chunk"])])
        assert agg.hit_rate == pytest.approx(0.0)

    def test_hit_gives_one_hit_rate(self):
        ev = self._evaluator(["doc_chunk_0000", "extra"])
        _, agg = ev.evaluate([make_sample(expected_chunk_ids=["doc_chunk_0000"])])
        assert agg.hit_rate == pytest.approx(1.0)

    def test_mrr_first_rank_is_one(self):
        ev = self._evaluator(["doc_chunk_0000"])
        _, agg = ev.evaluate([make_sample(expected_chunk_ids=["doc_chunk_0000"])])
        assert agg.mrr == pytest.approx(1.0)

    def test_empty_dataset_returns_zero_metrics(self):
        ev = self._evaluator([])
        _, agg = ev.evaluate([])
        assert agg.precision_at_k == 0.0
        assert agg.mrr == 0.0

    def test_latency_is_non_negative(self):
        ev = self._evaluator(["c1"])
        samples, _ = ev.evaluate([make_sample(expected_chunk_ids=["c1"])])
        assert all(s.latency_ms >= 0 for s in samples)


# ---------------------------------------------------------------------------
# GenerationEvaluator
# ---------------------------------------------------------------------------

class TestGenerationEvaluator:
    def _ev(self, generator=None, embedder=None, faithfulness_generator=None):
        from generation.prompt_builder import PromptBuilder
        return GenerationEvaluator(
            generator=generator or MockGenerator(),
            builder=PromptBuilder(),
            embedder=embedder or MockEmbedder(),
            faithfulness_generator=faithfulness_generator,
        )

    def test_evaluate_sample_returns_result(self):
        ev = self._ev()
        result = ev.evaluate_sample(
            make_sample(), retrieved_results=[make_result("c1")]
        )
        from evaluation.generation_evaluator import GenerationSampleResult
        assert isinstance(result, GenerationSampleResult)

    def test_semantic_similarity_is_one_for_identical_vectors(self):
        v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        ev = self._ev(embedder=MockEmbedder(v))
        result = ev.evaluate_sample(make_sample(), [])
        assert result.semantic_similarity == pytest.approx(1.0)

    def test_answer_words_counted(self):
        gen = MockGenerator(answer="word1 word2 word3")
        ev = self._ev(generator=gen)
        result = ev.evaluate_sample(make_sample(), [])
        assert result.answer_words == 3

    def test_faithfulness_none_when_no_judge(self):
        ev = self._ev(faithfulness_generator=None)
        result = ev.evaluate_sample(make_sample(), [make_result("c1")])
        assert result.faithful is None

    def test_faithful_true_when_judge_says_faithful(self):
        ev = self._ev(faithfulness_generator=MockGenerator(answer="FAITHFUL"))
        result = ev.evaluate_sample(make_sample(), [make_result("c1")])
        assert result.faithful is True

    def test_faithful_false_when_judge_says_unfaithful(self):
        ev = self._ev(faithfulness_generator=MockGenerator(answer="UNFAITHFUL"))
        result = ev.evaluate_sample(make_sample(), [make_result("c1")])
        assert result.faithful is False

    def test_aggregate_faithfulness_rate(self):
        ev = self._ev(faithfulness_generator=MockGenerator(answer="FAITHFUL"))
        samples = [make_sample(i, f"Q{i}?") for i in range(4)]
        results, agg = ev.evaluate(samples, {s.id: [make_result("c1")] for s in samples})
        assert agg.faithfulness_rate == pytest.approx(1.0)

    def test_aggregate_returns_none_faithfulness_when_no_judge(self):
        ev = self._ev()
        samples = [make_sample(i) for i in range(3)]
        _, agg = ev.evaluate(samples, {s.id: [] for s in samples})
        assert agg.faithfulness_rate is None


# ---------------------------------------------------------------------------
# BenchmarkRunner
# ---------------------------------------------------------------------------

class TestBenchmarkRunner:
    def _runner(self, retrieved_ids=None, answer="Answer.", faithfulness_answer=None):
        from generation.prompt_builder import PromptBuilder
        ids = retrieved_ids or ["doc_chunk_0000"]
        retriever = MockRetriever([make_result(i, r) for r, i in enumerate(ids, 1)])
        faith_gen = MockGenerator(faithfulness_answer) if faithfulness_answer else None
        return BenchmarkRunner(
            retriever=retriever,
            generator=MockGenerator(answer=answer),
            embedder=MockEmbedder(),
            builder=PromptBuilder(),
            dataset=[make_sample(i, f"Q{i}?", expected_chunk_ids=["doc_chunk_0000"]) for i in range(1, 4)],
            top_k=3,
            faithfulness_generator=faith_gen,
        )

    def test_run_returns_benchmark_result(self):
        result = self._runner().run()
        assert isinstance(result, BenchmarkResult)

    def test_result_has_correct_sample_count(self):
        result = self._runner().run()
        assert len(result.retrieval_samples) == 3
        assert len(result.generation_samples) == 3

    def test_timestamp_is_set(self):
        result = self._runner().run()
        assert len(result.timestamp) > 0

    def test_config_contains_top_k(self):
        result = self._runner().run()
        assert result.config["top_k"] == 3

    def test_retrieval_metrics_in_valid_range(self):
        result = self._runner().run()
        r = result.retrieval
        assert 0.0 <= r.precision_at_k <= 1.0
        assert 0.0 <= r.recall_at_k <= 1.0
        assert 0.0 <= r.hit_rate <= 1.0
        assert 0.0 <= r.mrr <= 1.0

    def test_faithfulness_populated_when_judge_present(self):
        result = self._runner(faithfulness_answer="FAITHFUL").run()
        assert result.generation.faithfulness_rate == pytest.approx(1.0)

    def test_faithfulness_none_without_judge(self):
        result = self._runner().run()
        assert result.generation.faithfulness_rate is None


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

class TestReportGenerator:
    def _result(self) -> BenchmarkResult:
        from generation.prompt_builder import PromptBuilder
        runner = BenchmarkRunner(
            retriever=MockRetriever([make_result("doc_chunk_0000")]),
            generator=MockGenerator(),
            embedder=MockEmbedder(),
            builder=PromptBuilder(),
            dataset=[make_sample(1, expected_chunk_ids=["doc_chunk_0000"])],
            top_k=3,
        )
        return runner.run()

    def test_save_csv_creates_file(self, tmp_path):
        rg = ReportGenerator(tmp_path)
        path = rg.save_csv(self._result())
        assert path.exists()

    def test_csv_has_rows(self, tmp_path):
        import csv as _csv
        rg = ReportGenerator(tmp_path)
        path = rg.save_csv(self._result())
        rows = list(_csv.DictReader(path.open(encoding="utf-8")))
        assert len(rows) == 1

    def test_csv_contains_expected_columns(self, tmp_path):
        import csv as _csv
        rg = ReportGenerator(tmp_path)
        path = rg.save_csv(self._result())
        row = next(_csv.DictReader(path.open(encoding="utf-8")))
        assert "question_id" in row
        assert "precision" in row
        assert "recall" in row
        assert "semantic_similarity" in row

    def test_save_summary_creates_file(self, tmp_path):
        rg = ReportGenerator(tmp_path)
        path = rg.save_summary(self._result())
        assert path.exists()

    def test_summary_contains_metric_headings(self, tmp_path):
        rg = ReportGenerator(tmp_path)
        path = rg.save_summary(self._result())
        content = path.read_text(encoding="utf-8")
        assert "Retrieval Metrics" in content
        assert "Generation Metrics" in content
        assert "MRR" in content

    def test_report_dir_created_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "reports"
        rg = ReportGenerator(nested)
        rg.save_csv(self._result())
        assert nested.exists()

    def test_experiment_csv_saved(self, tmp_path):
        rg = ReportGenerator(tmp_path)
        rows = [{"chunk_size": 256, "precision_at_5": 0.8}, {"chunk_size": 512, "precision_at_5": 0.9}]
        path = rg.save_experiment_csv(rows)
        assert path.exists()
