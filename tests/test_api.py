"""
Tests for the FastAPI application (Phase 7).

All tests override the `get_service` dependency with a MockRAGService so
that no real FAISS index, embedder, or LLM is required.  The TestClient
handles the ASGI lifecycle, including request/response serialisation.
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_service
from chunking.chunk import Chunk
from retrieval.ranking import RetrievalResult
from services.rag_service import RAGResponse


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

def _fake_result() -> RetrievalResult:
    chunk = Chunk(
        chunk_id="doc1_chunk_0",
        document_id="doc1",
        text="The Eiffel Tower is located in Paris, France.",
        start_char=0,
        end_char=46,
    )
    return RetrievalResult(chunk=chunk, score=0.92, rank=1)


class MockRAGService:
    """Fixed-response double that records every call for assertion."""

    def __init__(self, raise_exc: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._raise_exc = raise_exc

    def answer(self, question: str, top_k: int | None = None) -> RAGResponse:
        self.calls.append({"question": question, "top_k": top_k})
        if self._raise_exc is not None:
            raise self._raise_exc
        return RAGResponse(
            answer="Paris is the capital of France.",
            sources=[_fake_result()],
            retrieval_latency_ms=5.0,
            generation_latency_ms=120.0,
            request_id="test-request-id-abc123",
        )

    def get_metrics(self) -> dict:
        return {
            "total_queries": len(self.calls),
            "avg_retrieval_ms": 5.0,
            "avg_generation_ms": 120.0,
            "errors": 0,
        }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_service() -> MockRAGService:
    return MockRAGService()


@pytest.fixture
def client(mock_service: MockRAGService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_service] = lambda: mock_service
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200

    def test_body_is_healthy(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "healthy"}

    def test_no_service_dependency_needed(self) -> None:
        """Health check must not require a loaded pipeline."""
        app = create_app()
        # Deliberately do NOT override get_service — health should still pass
        # because it doesn't inject it.
        app.dependency_overrides[get_service] = lambda: None
        with TestClient(app) as c:
            assert c.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/metrics").status_code == 200

    def test_has_required_fields(self, client: TestClient) -> None:
        data = client.get("/metrics").json()
        for key in ("total_queries", "avg_retrieval_ms", "avg_generation_ms", "errors"):
            assert key in data, f"metrics missing key: {key}"

    def test_total_queries_is_integer(self, client: TestClient) -> None:
        assert isinstance(client.get("/metrics").json()["total_queries"], int)

    def test_errors_is_integer(self, client: TestClient) -> None:
        assert isinstance(client.get("/metrics").json()["errors"], int)

    def test_503_when_service_unavailable(self) -> None:
        def raise_503():
            raise HTTPException(status_code=503, detail="Index not available")

        app = create_app()
        app.dependency_overrides[get_service] = raise_503
        with TestClient(app) as c:
            assert c.get("/metrics").status_code == 503


# ---------------------------------------------------------------------------
# POST /query — happy path
# ---------------------------------------------------------------------------

class TestQueryEndpointSuccess:
    def test_valid_question_returns_200(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": "Where is the Eiffel Tower?"})
        assert resp.status_code == 200

    def test_answer_field_matches_mock(self, client: TestClient) -> None:
        data = client.post("/query", json={"question": "Where is the Eiffel Tower?"}).json()
        assert data["answer"] == "Paris is the capital of France."

    def test_sources_is_non_empty_list(self, client: TestClient) -> None:
        data = client.post("/query", json={"question": "Where?"}).json()
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) == 1

    def test_source_has_required_fields(self, client: TestClient) -> None:
        src = client.post("/query", json={"question": "Where?"}).json()["sources"][0]
        assert src["document_id"] == "doc1"
        assert src["chunk_id"] == "doc1_chunk_0"
        assert isinstance(src["score"], float)

    def test_latency_fields_non_negative(self, client: TestClient) -> None:
        data = client.post("/query", json={"question": "test"}).json()
        assert data["retrieval_latency_ms"] >= 0
        assert data["generation_latency_ms"] >= 0
        assert data["total_latency_ms"] >= 0

    def test_total_latency_equals_sum(self, client: TestClient) -> None:
        data = client.post("/query", json={"question": "test"}).json()
        expected = round(data["retrieval_latency_ms"] + data["generation_latency_ms"], 1)
        assert abs(data["total_latency_ms"] - expected) < 0.05

    def test_request_id_non_empty(self, client: TestClient) -> None:
        data = client.post("/query", json={"question": "test"}).json()
        assert data["request_id"] == "test-request-id-abc123"

    def test_custom_top_k_forwarded_to_service(
        self, client: TestClient, mock_service: MockRAGService
    ) -> None:
        client.post("/query", json={"question": "test", "top_k": 3})
        assert mock_service.calls[-1]["top_k"] == 3

    def test_default_top_k_when_omitted(
        self, client: TestClient, mock_service: MockRAGService
    ) -> None:
        from config.settings import TOP_K

        client.post("/query", json={"question": "test"})
        assert mock_service.calls[-1]["top_k"] == TOP_K

    def test_question_forwarded_to_service(
        self, client: TestClient, mock_service: MockRAGService
    ) -> None:
        client.post("/query", json={"question": "What is the capital?"})
        assert mock_service.calls[-1]["question"] == "What is the capital?"


# ---------------------------------------------------------------------------
# POST /query — validation errors (422)
# ---------------------------------------------------------------------------

class TestQueryValidation:
    def test_missing_question_field_is_422(self, client: TestClient) -> None:
        assert client.post("/query", json={}).status_code == 422

    def test_empty_question_string_rejected(self, client: TestClient) -> None:
        # Pydantic min_length=1 fires before the route function
        resp = client.post("/query", json={"question": ""})
        assert resp.status_code in (400, 422)

    def test_whitespace_only_question_rejected(self, client: TestClient) -> None:
        # str_strip_whitespace=True collapses "   " to "", failing min_length
        resp = client.post("/query", json={"question": "   "})
        assert resp.status_code in (400, 422)

    def test_top_k_zero_is_422(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": "test", "top_k": 0})
        assert resp.status_code == 422

    def test_top_k_exceeds_max_is_422(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": "test", "top_k": 100})
        assert resp.status_code == 422

    def test_non_json_body_is_422(self, client: TestClient) -> None:
        resp = client.post(
            "/query", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 422

    def test_question_must_be_string(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": 42})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /query — service-level error propagation
# ---------------------------------------------------------------------------

class TestQueryErrorHandling:
    def test_503_when_dependency_raises(self) -> None:
        def raise_503():
            raise HTTPException(status_code=503, detail="Index not available")

        app = create_app()
        app.dependency_overrides[get_service] = raise_503
        with TestClient(app) as c:
            resp = c.post("/query", json={"question": "test"})
        assert resp.status_code == 503

    def test_504_on_timeout_error(self) -> None:
        mock = MockRAGService(raise_exc=TimeoutError("LLM timed out"))
        app = create_app()
        app.dependency_overrides[get_service] = lambda: mock
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/query", json={"question": "test"})
        assert resp.status_code == 504

    def test_500_on_unexpected_service_error(self) -> None:
        mock = MockRAGService(raise_exc=RuntimeError("Something broke"))
        app = create_app()
        app.dependency_overrides[get_service] = lambda: mock
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/query", json={"question": "test"})
        assert resp.status_code == 500

    def test_503_detail_preserved(self) -> None:
        def raise_503():
            raise HTTPException(status_code=503, detail="custom message")

        app = create_app()
        app.dependency_overrides[get_service] = raise_503
        with TestClient(app) as c:
            resp = c.post("/query", json={"question": "test"})
        assert "custom message" in resp.json()["detail"]
