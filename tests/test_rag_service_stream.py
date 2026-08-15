"""Tests for RAGService.stream — the real service, not a mock of it.

tests/test_stream.py covers the HTTP framing by substituting the whole service,
so nothing there exercises the event sequence, the latency accounting or the
metrics side effects. This does.
"""

import uuid
from typing import Generator, List, Optional

import pytest

from chunking.chunk import Chunk
from generation.prompt_builder import Prompt
from retrieval.pipeline import PipelineStage
from retrieval.ranking import RetrievalResult
from services.rag_service import RAGService


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _result(index: int = 0) -> RetrievalResult:
    return RetrievalResult(
        chunk=Chunk(
            chunk_id=f"doc_chunk_{index}",
            document_id="doc",
            text="Durability means committed data survives a crash.",
            start_char=0,
            end_char=48,
        ),
        score=0.9 - index / 10,
        rank=index + 1,
    )


class FakeRetriever:
    def __init__(self, results: Optional[List[RetrievalResult]] = None, raises=None):
        self.results = [_result(0), _result(1)] if results is None else results
        self.raises = raises
        self.last_top_k: Optional[int] = None
        self.last_mode: Optional[str] = None

    def retrieve(
        self, question: str, top_k: int, mode: str = "hybrid"
    ) -> List[RetrievalResult]:
        results, _ = self.retrieve_traced(question, top_k, mode)
        return results

    def retrieve_traced(self, question: str, top_k: int, mode: str = "hybrid"):
        if self.raises:
            raise self.raises
        self.last_top_k = top_k
        self.last_mode = mode
        return self.results, [
            PipelineStage(name="embedding", status="ok", latency_ms=0.1),
            PipelineStage(
                name="dense",
                status="ok",
                latency_ms=0.2,
                candidates_in=19,
                candidates_out=len(self.results),
            ),
        ]


class FakeBuilder:
    def build(self, question: str, results: List[RetrievalResult]) -> Prompt:
        return Prompt(system="system", user=question)


class FakeGenerator:
    def __init__(self, tokens: Optional[List[str]] = None, raises_after: Optional[int] = None):
        self.tokens = ["Durability", " means", " persistence."] if tokens is None else tokens
        self.raises_after = raises_after

    def stream(self, prompt: Prompt, sources: List[RetrievalResult]) -> Generator[str, None, None]:
        for i, token in enumerate(self.tokens):
            if self.raises_after is not None and i == self.raises_after:
                raise RuntimeError("upstream died mid-generation")
            yield token


def build_service(retriever=None, generator=None) -> RAGService:
    return RAGService(
        retriever=retriever or FakeRetriever(),
        generator=generator or FakeGenerator(),
        builder=FakeBuilder(),
        default_top_k=5,
    )


def drain(service: RAGService, question: str = "what is durability?", **kwargs) -> List[dict]:
    return list(service.stream(question, **kwargs))


# ---------------------------------------------------------------------------
# Event sequence
# ---------------------------------------------------------------------------


class TestEventSequence:
    def test_sources_arrive_before_any_token(self):
        # The UI shows what was retrieved while the answer is still generating;
        # sources arriving last would defeat the point of streaming.
        events = drain(build_service())
        assert events[0]["type"] == "sources"
        assert [e["type"] for e in events].index("token") > 0

    def test_tokens_are_emitted_individually(self):
        events = drain(build_service(generator=FakeGenerator(["a", "b", "c"])))
        assert [e["data"] for e in events if e["type"] == "token"] == ["a", "b", "c"]

    def test_last_event_is_done(self):
        assert drain(build_service())[-1]["type"] == "done"

    def test_sources_carry_attribution_and_score(self):
        source = drain(build_service())[0]["data"][0]
        assert source["document_id"] == "doc"
        assert source["chunk_id"] == "doc_chunk_0"
        assert source["score"] == pytest.approx(0.9)
        assert source["rank"] == 1

    def test_sources_carry_the_chunk_text(self):
        # The retrieval table has to show what was retrieved; an id alone is
        # not inspectable.
        source = drain(build_service())[0]["data"][0]
        assert source["text"] == "Durability means committed data survives a crash."

    def test_sources_carry_a_per_stage_breakdown(self):
        source = drain(build_service())[0]["data"][0]
        assert set(source["scores"]) == {"dense", "sparse", "fused", "reranker"}

    def test_top_k_reaches_the_retriever(self):
        retriever = FakeRetriever()
        drain(build_service(retriever=retriever), top_k=11)
        assert retriever.last_top_k == 11

    def test_default_top_k_is_used_when_unspecified(self):
        retriever = FakeRetriever()
        drain(build_service(retriever=retriever))
        assert retriever.last_top_k == 5

    def test_retriever_choice_reaches_the_retriever(self):
        retriever = FakeRetriever()
        drain(build_service(retriever=retriever), retriever="sparse")
        assert retriever.last_mode == "sparse"


# ---------------------------------------------------------------------------
# The done payload
# ---------------------------------------------------------------------------


class TestDonePayload:
    def _done(self, service=None) -> dict:
        return drain(service or build_service())[-1]["data"]

    def test_carries_a_request_id(self):
        # Without it the id in the server log has nothing to join against.
        uuid.UUID(self._done()["request_id"])

    def test_request_id_is_unique_per_stream(self):
        service = build_service()
        assert drain(service)[-1]["data"]["request_id"] != drain(service)[-1]["data"]["request_id"]

    def test_reports_the_same_latency_breakdown_as_the_non_streaming_path(self):
        done = self._done()
        assert set(done) == {
            "request_id",
            "retriever",
            "retrieval_latency_ms",
            "generation_latency_ms",
            "total_latency_ms",
            "first_token_latency_ms",
            "pipeline",
            "abstained",
        }

    def test_reports_whether_the_model_abstained(self):
        # The prompt names the exact sentence to reply with when the context
        # cannot answer, so this is a contract check the server owns rather
        # than something the client should infer from the text.
        assert self._done()["abstained"] is False

    def test_detects_the_abstention_sentinel(self):
        service = build_service(generator=FakeGenerator(["I don't", " know."]))
        assert drain(service)[-1]["data"]["abstained"] is True

    def test_carries_the_pipeline(self):
        stages = self._done()["pipeline"]
        assert [s["name"] for s in stages] == [
            "embedding",
            "dense",
            "sparse",
            "fusion",
            "reranker",
            "generation",
        ]

    def test_generation_is_reported_as_a_stage(self):
        generation = next(
            s for s in self._done()["pipeline"] if s["name"] == "generation"
        )
        assert generation["status"] == "ok"
        assert generation["candidates_in"] == 2
        # Generation emits prose, not a shortlist.
        assert generation["candidates_out"] is None

    def test_echoes_which_retriever_ran(self):
        # Without this a null stage in a chunk's trace is ambiguous.
        assert self._done()["retriever"] == "hybrid"

    def test_total_is_the_sum_of_its_parts(self):
        done = self._done()
        assert done["total_latency_ms"] == pytest.approx(
            done["retrieval_latency_ms"] + done["generation_latency_ms"], abs=0.2
        )

    def test_time_to_first_token_is_measured(self):
        done = self._done()
        assert done["first_token_latency_ms"] is not None
        # It precedes the end of generation by definition.
        assert done["first_token_latency_ms"] <= done["generation_latency_ms"] + 0.2

    def test_time_to_first_token_is_null_when_nothing_was_generated(self):
        # Distinct from zero, which would claim a token arrived instantly.
        done = self._done(build_service(generator=FakeGenerator([])))
        assert done["first_token_latency_ms"] is None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_a_streamed_query_is_counted(self):
        # /metrics reporting zero while the UI streams every answer would be a
        # measurement platform misreporting its own workload.
        service = build_service()
        drain(service)
        assert service.get_metrics()["total_queries"] == 1

    def test_counting_happens_once_per_stream(self):
        service = build_service()
        drain(service)
        drain(service)
        assert service.get_metrics()["total_queries"] == 2

    def test_latency_averages_are_populated(self):
        service = build_service()
        drain(service)
        metrics = service.get_metrics()
        assert metrics["avg_generation_ms"] >= 0
        assert metrics["avg_retrieval_ms"] >= 0

    def test_a_failure_is_counted_as_an_error(self):
        service = build_service(retriever=FakeRetriever(raises=RuntimeError("index gone")))
        with pytest.raises(RuntimeError):
            drain(service)
        assert service.get_metrics()["errors"] == 1

    def test_a_failure_is_not_counted_as_a_success(self):
        service = build_service(generator=FakeGenerator(raises_after=1))
        with pytest.raises(RuntimeError):
            drain(service)
        assert service.get_metrics()["total_queries"] == 0


# ---------------------------------------------------------------------------
# Failure part-way through
# ---------------------------------------------------------------------------


class TestMidStreamFailure:
    def test_tokens_emitted_before_the_failure_still_reached_the_client(self):
        # The client is told to keep a partial answer; that is only meaningful
        # if the service really does emit tokens before it fails.
        service = build_service(generator=FakeGenerator(["one", "two", "three"], raises_after=2))
        emitted = []
        with pytest.raises(RuntimeError):
            for event in service.stream("q"):
                emitted.append(event)

        assert [e["data"] for e in emitted if e["type"] == "token"] == ["one", "two"]

    def test_no_done_event_is_emitted_on_failure(self):
        # 'done' means the answer is complete. Emitting it after a failure would
        # present a truncated answer as a finished one.
        service = build_service(generator=FakeGenerator(["one"], raises_after=0))
        emitted = []
        with pytest.raises(RuntimeError):
            for event in service.stream("q"):
                emitted.append(event)

        assert not [e for e in emitted if e["type"] == "done"]
