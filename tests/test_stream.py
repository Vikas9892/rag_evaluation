"""Tests for the POST /stream Server-Sent Events endpoint."""
import json
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_service
from chunking.chunk import Chunk
from retrieval.ranking import RetrievalResult


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

def _fake_result() -> RetrievalResult:
    return RetrievalResult(
        chunk=Chunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            text="Streaming is the future.",
            start_char=0,
            end_char=25,
        ),
        score=0.88,
        rank=1,
    )


class MockStreamingService:
    """Yields a fixed event sequence: sources → two tokens → done."""

    def stream(self, question: str, top_k: int | None = None) -> Generator[dict, None, None]:
        yield {
            "type": "sources",
            "data": [
                {"document_id": "doc1", "chunk_id": "doc1_chunk_0", "score": 0.88}
            ],
        }
        yield {"type": "token", "data": "Hello"}
        yield {"type": "token", "data": " world"}
        yield {"type": "done"}

    def get_metrics(self) -> dict:
        return {"total_queries": 0, "avg_retrieval_ms": 0, "avg_generation_ms": 0, "errors": 0}


class MockErrorService:
    """Raises NotImplementedError from stream() to simulate a non-streaming generator."""

    def stream(self, question: str, top_k: int | None = None) -> Generator[dict, None, None]:
        raise NotImplementedError("Generator does not support streaming")
        yield  # make it a generator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = create_app()
    app.dependency_overrides[get_service] = lambda: MockStreamingService()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def error_client():
    app = create_app()
    app.dependency_overrides[get_service] = lambda: MockErrorService()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# SSE format
# ---------------------------------------------------------------------------

def _parse_sse(raw: str) -> list[dict]:
    """Parse 'data: {...}\\n\\n' lines from a raw SSE response body."""
    events = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStreamEndpoint:
    def test_returns_200(self, client):
        resp = client.post("/stream", json={"question": "test"})
        assert resp.status_code == 200

    def test_content_type_is_event_stream(self, client):
        resp = client.post("/stream", json={"question": "test"})
        assert "text/event-stream" in resp.headers["content-type"]

    def test_first_event_is_sources(self, client):
        resp = client.post("/stream", json={"question": "test"})
        events = _parse_sse(resp.text)
        assert events[0]["type"] == "sources"

    def test_sources_event_has_data_list(self, client):
        resp = client.post("/stream", json={"question": "test"})
        events = _parse_sse(resp.text)
        assert isinstance(events[0]["data"], list)

    def test_token_events_present(self, client):
        resp = client.post("/stream", json={"question": "test"})
        events = _parse_sse(resp.text)
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) == 2

    def test_token_data_concatenates_to_answer(self, client):
        resp = client.post("/stream", json={"question": "test"})
        events = _parse_sse(resp.text)
        tokens = "".join(e["data"] for e in events if e["type"] == "token")
        assert tokens == "Hello world"

    def test_last_event_is_done(self, client):
        resp = client.post("/stream", json={"question": "test"})
        events = _parse_sse(resp.text)
        assert events[-1]["type"] == "done"

    def test_empty_question_returns_400(self, client):
        resp = client.post("/stream", json={"question": ""})
        assert resp.status_code in (400, 422)

    def test_missing_question_returns_422(self, client):
        assert client.post("/stream", json={}).status_code == 422

    def test_not_implemented_yields_error_event(self, error_client):
        resp = error_client.post("/stream", json={"question": "test"})
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
