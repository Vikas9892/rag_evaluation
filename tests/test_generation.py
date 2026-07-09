"""Unit tests for Phase 5 — generation pipeline."""
import sys
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chunking.chunk import Chunk
from retrieval.ranking import RetrievalResult
from generation.models import GenerationResponse, Prompt
from generation.prompt_builder import PromptBuilder, SYSTEM_PROMPT
from generation.generator import BaseGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_chunk(idx: int = 0, doc_id: str = "os.pdf") -> Chunk:
    return Chunk(
        chunk_id=f"{doc_id}_chunk_{idx:04d}",
        document_id=doc_id,
        text=f"Deadlock occurs when process {idx} waits indefinitely for resources.",
        start_char=idx * 80,
        end_char=idx * 80 + 70,
        metadata={"source": doc_id, "chunk_index": idx, "strategy": "recursive"},
    )


def make_result(idx: int = 0, score: float = 0.9) -> RetrievalResult:
    return RetrievalResult(chunk=make_chunk(idx), score=score, rank=idx + 1)


def make_results(n: int) -> List[RetrievalResult]:
    return [make_result(i, score=round(0.95 - i * 0.05, 2)) for i in range(n)]


# ---------------------------------------------------------------------------
# MockGenerator — implements BaseGenerator without any real API call
# ---------------------------------------------------------------------------

class MockGenerator(BaseGenerator):
    def __init__(
        self,
        answer: str = "Deadlock is a condition where processes wait indefinitely.",
        prompt_tokens: int = 120,
        completion_tokens: int = 40,
        latency_ms: float = 55.0,
    ) -> None:
        self._answer = answer
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._latency_ms = latency_ms
        self.last_prompt: Prompt | None = None

    def generate(
        self, prompt: Prompt, sources: List[RetrievalResult]
    ) -> GenerationResponse:
        self.last_prompt = prompt  # capture for inspection
        return GenerationResponse(
            answer=self._answer,
            sources=sources,
            prompt_tokens=self._prompt_tokens,
            completion_tokens=self._completion_tokens,
            latency_ms=self._latency_ms,
        )


# ---------------------------------------------------------------------------
# Prompt dataclass
# ---------------------------------------------------------------------------

class TestPrompt:
    def test_fields_are_set(self):
        p = Prompt(system="sys", user="usr")
        assert p.system == "sys"
        assert p.user == "usr"

    def test_equality(self):
        assert Prompt("a", "b") == Prompt("a", "b")

    def test_inequality(self):
        assert Prompt("a", "b") != Prompt("a", "c")


# ---------------------------------------------------------------------------
# GenerationResponse dataclass
# ---------------------------------------------------------------------------

class TestGenerationResponse:
    def _response(self, **overrides) -> GenerationResponse:
        defaults = dict(
            answer="Deadlock requires four conditions.",
            sources=[make_result()],
            prompt_tokens=100,
            completion_tokens=30,
            latency_ms=250.0,
        )
        defaults.update(overrides)
        return GenerationResponse(**defaults)

    def test_fields_are_set(self):
        r = self._response()
        assert r.answer == "Deadlock requires four conditions."
        assert len(r.sources) == 1
        assert r.prompt_tokens == 100
        assert r.completion_tokens == 30
        assert r.latency_ms == 250.0

    def test_total_tokens_property(self):
        r = self._response(prompt_tokens=150, completion_tokens=50)
        assert r.total_tokens == 200

    def test_total_tokens_zero(self):
        r = self._response(prompt_tokens=0, completion_tokens=0)
        assert r.total_tokens == 0

    def test_sources_list_is_preserved(self):
        results = make_results(3)
        r = self._response(sources=results)
        assert len(r.sources) == 3
        assert r.sources[0].chunk.chunk_id == results[0].chunk.chunk_id


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class TestPromptBuilder:
    def test_returns_prompt_object(self):
        p = PromptBuilder().build("What is deadlock?", make_results(2))
        assert isinstance(p, Prompt)

    def test_question_appears_in_user_prompt(self):
        question = "What is deadlock?"
        p = PromptBuilder().build(question, make_results(2))
        assert question in p.user

    def test_chunk_text_appears_in_user_prompt(self):
        result = make_result(0)
        p = PromptBuilder().build("q", [result])
        assert result.chunk.text in p.user

    def test_system_prompt_contains_i_dont_know_instruction(self):
        assert "I don't know" in SYSTEM_PROMPT

    def test_system_prompt_contains_only_context_rule(self):
        assert "ONLY" in SYSTEM_PROMPT

    def test_system_prompt_is_constant_across_calls(self):
        b = PromptBuilder()
        p1 = b.build("q1", make_results(1))
        p2 = b.build("q2", make_results(1))
        assert p1.system == p2.system == SYSTEM_PROMPT

    def test_sources_are_labeled_sequentially(self):
        p = PromptBuilder().build("q", make_results(3))
        assert "[Source 1]" in p.user
        assert "[Source 2]" in p.user
        assert "[Source 3]" in p.user

    def test_document_id_appears_in_each_source_label(self):
        result = make_result(0, score=0.9)
        p = PromptBuilder().build("q", [result])
        assert result.chunk.document_id in p.user

    def test_empty_results_produces_valid_prompt(self):
        p = PromptBuilder().build("What is CPU?", [])
        assert "What is CPU?" in p.user
        assert "(no context provided)" in p.user

    def test_max_context_chunks_limits_sources(self):
        p = PromptBuilder(max_context_chunks=2).build("q", make_results(5))
        assert "[Source 1]" in p.user
        assert "[Source 2]" in p.user
        assert "[Source 3]" not in p.user

    def test_max_context_chunks_respected_when_fewer_available(self):
        # Should not crash when results < max_context_chunks
        p = PromptBuilder(max_context_chunks=10).build("q", make_results(2))
        assert "[Source 1]" in p.user
        assert "[Source 2]" in p.user
        assert "[Source 3]" not in p.user

    def test_answer_label_in_user_prompt(self):
        p = PromptBuilder().build("q", make_results(1))
        assert "Answer:" in p.user

    def test_context_label_in_user_prompt(self):
        p = PromptBuilder().build("q", make_results(1))
        assert "Context:" in p.user

    def test_sources_separated_by_divider(self):
        p = PromptBuilder().build("q", make_results(2))
        assert "---" in p.user


# ---------------------------------------------------------------------------
# MockGenerator
# ---------------------------------------------------------------------------

class TestMockGenerator:
    def test_returns_generation_response(self):
        resp = MockGenerator().generate(Prompt("sys", "usr"), make_results(2))
        assert isinstance(resp, GenerationResponse)

    def test_sources_attached_to_response(self):
        results = make_results(3)
        resp = MockGenerator().generate(Prompt("s", "u"), results)
        assert resp.sources is results

    def test_custom_answer_returned(self):
        resp = MockGenerator(answer="Custom.").generate(Prompt("s", "u"), [])
        assert resp.answer == "Custom."

    def test_token_counts_set(self):
        resp = MockGenerator(prompt_tokens=50, completion_tokens=20).generate(
            Prompt("s", "u"), []
        )
        assert resp.prompt_tokens == 50
        assert resp.completion_tokens == 20

    def test_latency_set(self):
        resp = MockGenerator(latency_ms=99.0).generate(Prompt("s", "u"), [])
        assert resp.latency_ms == 99.0

    def test_mock_is_base_generator_subclass(self):
        assert isinstance(MockGenerator(), BaseGenerator)

    def test_last_prompt_captured(self):
        gen = MockGenerator()
        prompt = Prompt("sys", "usr")
        gen.generate(prompt, [])
        assert gen.last_prompt is prompt


# ---------------------------------------------------------------------------
# Integration — PromptBuilder + MockGenerator
# ---------------------------------------------------------------------------

class TestRAGPipelineIntegration:
    def test_full_pipeline_returns_answer(self):
        results = make_results(3)
        prompt = PromptBuilder().build("What causes deadlock?", results)
        response = MockGenerator().generate(prompt, results)
        assert isinstance(response.answer, str)
        assert len(response.answer) > 0

    def test_sources_in_response_match_retrieval_results(self):
        results = make_results(3)
        prompt = PromptBuilder().build("q", results)
        response = MockGenerator().generate(prompt, results)
        assert len(response.sources) == 3
        for original, source in zip(results, response.sources):
            assert source.chunk.chunk_id == original.chunk.chunk_id

    def test_prompt_contains_all_retrieved_texts(self):
        results = make_results(3)
        prompt = PromptBuilder().build("What is deadlock?", results)
        for r in results:
            assert r.chunk.text in prompt.user

    def test_top_k_respected_in_prompt(self):
        results = make_results(5)
        gen = MockGenerator()
        prompt = PromptBuilder(max_context_chunks=3).build("q", results)
        gen.generate(prompt, results[:3])
        # Only first 3 source labels should be in the prompt
        assert "[Source 3]" in prompt.user
        assert "[Source 4]" not in prompt.user

    def test_response_total_tokens(self):
        prompt = PromptBuilder().build("q", make_results(1))
        resp = MockGenerator(prompt_tokens=100, completion_tokens=50).generate(
            prompt, make_results(1)
        )
        assert resp.total_tokens == 150

    def test_prompt_is_separate_from_generation(self):
        """PromptBuilder and Generator are independently testable — swapping
        the generator never requires touching the prompt builder."""
        results = make_results(2)
        prompt = PromptBuilder().build("What is CPU scheduling?", results)

        gen1 = MockGenerator(answer="Answer A")
        gen2 = MockGenerator(answer="Answer B")

        r1 = gen1.generate(prompt, results)
        r2 = gen2.generate(prompt, results)

        assert r1.answer == "Answer A"
        assert r2.answer == "Answer B"
        # Both used the exact same prompt
        assert gen1.last_prompt is gen2.last_prompt is prompt
