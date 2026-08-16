"""Tests for the config, deep-health, evaluation and benchmark endpoints.

These run against a stub service rather than a real index: the endpoints' job is
shaping and caching, and binding them to the shipped corpus would make them a
slow re-test of the retriever.
"""

from typing import List

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_service
from api.routers import evaluation as evaluation_router
from chunking.chunk import Chunk
from retrieval.ranking import RetrievalResult


def _chunk(cid: str) -> Chunk:
    return Chunk(
        chunk_id=cid,
        document_id="dbms.md",
        text="acid durability",
        start_char=0,
        end_char=15,
    )


class StubRetriever:
    """Returns the expected chunk first for odd questions, last for even ones."""

    def __init__(self) -> None:
        self.calls: List[dict] = []

    def retrieve(
        self, question: str, top_k: int, mode: str = "hybrid", reranker: bool = False
    ):
        self.calls.append(
            {"question": question, "top_k": top_k, "mode": mode, "reranker": reranker}
        )
        ids = [f"c{i}" for i in range(top_k)]
        return [
            RetrievalResult(chunk=_chunk(cid), score=1.0 - i / 10, rank=i + 1)
            for i, cid in enumerate(ids)
        ]


class StubService:
    def __init__(self) -> None:
        self._retriever = StubRetriever()

    @property
    def retriever(self):
        return self._retriever

    def corpus_size(self) -> int:
        return 19

    def document_count(self) -> int:
        return 3

    def get_metrics(self) -> dict:
        return {
            "total_queries": 0,
            "avg_retrieval_ms": 0,
            "avg_generation_ms": 0,
            "errors": 0,
        }


@pytest.fixture(autouse=True)
def clear_cache():
    evaluation_router._cache.clear()
    yield
    evaluation_router._cache.clear()


@pytest.fixture
def service() -> StubService:
    return StubService()


@pytest.fixture
def client(service: StubService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app) as c:
        yield c


class TestConfig:
    def test_reports_the_corpus_it_indexed(self, client):
        body = client.get("/config").json()
        assert body["indexed_chunks"] == 19
        assert body["documents"] == 3

    def test_lists_the_retrievers_the_api_accepts(self, client):
        assert client.get("/config").json()["retrievers"] == [
            "dense",
            "sparse",
            "hybrid",
        ]

    def test_reports_the_reranker_as_off(self, client):
        # It is implemented but not in the live path, and the pipeline trace
        # says skipped. Claiming otherwise here would contradict that.
        assert client.get("/config").json()["reranker_enabled"] is False

    def test_exposes_the_models_rather_than_leaving_the_ui_to_hardcode_them(
        self, client
    ):
        body = client.get("/config").json()
        assert body["embedding_model"]
        assert body["llm_model"]


class TestDeepHealth:
    def test_checks_every_dependency(self, client):
        names = {c["name"] for c in client.get("/health/deep").json()["checks"]}
        assert names == {"index", "groq_api_key", "disk"}

    def test_reports_passing_checks_too(self, client):
        # An operator needs to see what was verified, not only what broke.
        checks = client.get("/health/deep").json()["checks"]
        assert all(c["detail"] for c in checks)

    def test_a_missing_api_key_degrades_rather_than_fails(self, client, monkeypatch):
        # Retrieval and evaluation work without it; only generation does not.
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        body = client.get("/health/deep").json()
        key = next(c for c in body["checks"] if c["name"] == "groq_api_key")

        assert key["status"] == "warn"
        assert body["status"] == "degraded"

    def test_the_shallow_probe_stays_cheap(self, client, monkeypatch):
        # A load-balancer probe must not start failing because a downstream key
        # is missing.
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert client.get("/health").json()["status"] == "healthy"


class TestEvaluation:
    def test_returns_metrics_and_a_per_question_breakdown(self, client):
        body = client.get("/evaluation").json()
        assert set(body["metrics"]) == {
            "precision_at_k",
            "recall_at_k",
            "hit_rate",
            "mrr",
            "avg_latency_ms",
            "p50_latency_ms",
            "p95_latency_ms",
        }
        assert len(body["questions"]) == body["dataset_size"]

    def test_reports_the_latency_tail_alongside_the_mean(self, client):
        metrics = client.get("/evaluation").json()["metrics"]

        # The mean alone hides the tail, and the tail is what a waiting user
        # meets. p95 can equal p50 on a flat distribution, never precede it.
        assert metrics["p95_latency_ms"] >= metrics["p50_latency_ms"]

    def test_the_same_metrics_reach_benchmarks(self, client):
        # Both endpoints build RetrievalMetrics from the same helper, so a new
        # metric cannot land on one and silently miss the other.
        evaluation = set(client.get("/evaluation").json()["metrics"])
        cells = client.get("/benchmarks").json()["cells"]

        assert cells, "no benchmark cells to check"
        assert set(cells[0]["metrics"]) == evaluation

    def test_honours_the_requested_retriever(self, client, service):
        client.get("/evaluation?retriever=sparse")
        assert {c["mode"] for c in service.retriever.calls} == {"sparse"}

    def test_honours_the_requested_top_k(self, client, service):
        client.get("/evaluation?top_k=7")
        assert {c["top_k"] for c in service.retriever.calls} == {7}

    def test_rejects_a_top_k_the_pipeline_will_not_accept(self, client):
        assert client.get("/evaluation?top_k=500").status_code == 422

    def test_rejects_an_unknown_retriever(self, client):
        assert client.get("/evaluation?retriever=magic").status_code == 422

    def test_makes_no_llm_call(self, client, service):
        # Measuring retrieval must not cost generation budget.
        client.get("/evaluation")
        assert service.retriever.calls  # retrieval happened
        # StubService has no generator at all, so reaching one would error.


class TestEvaluationCache:
    def test_a_repeated_run_is_served_from_cache(self, client, service):
        client.get("/evaluation")
        first = len(service.retriever.calls)
        body = client.get("/evaluation").json()

        assert body["cached"] is True
        assert len(service.retriever.calls) == first

    def test_the_first_run_is_not_reported_as_cached(self, client):
        assert client.get("/evaluation").json()["cached"] is False

    def test_a_different_config_is_a_different_entry(self, client, service):
        client.get("/evaluation?top_k=3")
        before = len(service.retriever.calls)
        client.get("/evaluation?top_k=10")

        assert len(service.retriever.calls) > before

    def test_the_reranker_flag_is_part_of_the_cache_key(self, client, service):
        # Otherwise a reranked run would be served the unreranked result.
        client.get("/evaluation")
        before = len(service.retriever.calls)
        client.get("/evaluation?reranker=true")

        assert len(service.retriever.calls) > before


class TestBenchmarks:
    def test_sweeps_every_retriever_top_k_and_reranker(self, client):
        cells = client.get("/benchmarks").json()["cells"]
        assert len(cells) == 18  # 3 retrievers x 3 top-K x reranker on/off
        assert {c["retriever"] for c in cells} == {"dense", "sparse", "hybrid"}
        assert {c["top_k"] for c in cells} == {3, 5, 10}
        assert {c["reranker"] for c in cells} == {True, False}

    def test_the_reranker_is_swept_rather_than_assumed(self, client, service):
        # Whether the cross-encoder earns its latency is exactly the kind of
        # question this platform exists to answer.
        client.get("/benchmarks")
        assert {c["reranker"] for c in service.retriever.calls} == {True, False}

    def test_reports_whether_the_matrix_discriminates(self, client):
        # Every configuration scoring the same means the corpus is being
        # measured, not the retriever. The UI must be able to say so.
        assert "discriminating" in client.get("/benchmarks").json()

    def test_a_stub_that_ignores_the_config_does_not_discriminate(self, client):
        # The stub returns the same ranking whatever it is asked, so the matrix
        # is flat — which is exactly the case the flag exists to catch.
        assert client.get("/benchmarks").json()["discriminating"] is False

    def test_a_bounded_call_reports_what_is_still_pending(self, client, monkeypatch):
        # A full sweep takes minutes; a request that long does not survive a
        # proxy, a load balancer, or a client that hangs up.
        monkeypatch.setattr(evaluation_router, "_BENCHMARK_BUDGET_SECONDS", -1)
        body = client.get("/benchmarks").json()

        assert body["pending"] > 0
        assert body["cached"] is False

    def test_a_partial_matrix_never_claims_to_discriminate(self, client, monkeypatch):
        # Two cells that happen to tie are not evidence about the other sixteen.
        monkeypatch.setattr(evaluation_router, "_BENCHMARK_BUDGET_SECONDS", -1)
        assert client.get("/benchmarks").json()["discriminating"] is False

    def test_repeated_calls_fill_the_matrix_in(self, client, monkeypatch):
        monkeypatch.setattr(evaluation_router, "_BENCHMARK_BUDGET_SECONDS", -1)
        client.get("/benchmarks")
        monkeypatch.setattr(evaluation_router, "_BENCHMARK_BUDGET_SECONDS", 60)

        body = client.get("/benchmarks").json()
        assert body["pending"] == 0
        assert len(body["cells"]) == 18

    def test_reuses_the_evaluation_cache(self, client, service):
        client.get("/benchmarks")
        after_matrix = len(service.retriever.calls)
        client.get("/evaluation?top_k=5&retriever=hybrid")

        assert len(service.retriever.calls) == after_matrix
