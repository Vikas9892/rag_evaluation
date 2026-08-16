"""Tests for the pipeline trace behind the visualisation.

The product spec's rule for the diagram is that it must reflect what actually
executed and never animate a stage that did not run. That is only enforceable if
the backend reports execution rather than the frontend inferring it, so these
tests are mostly about the difference between "ran" and "did not".
"""

from typing import List

import pytest

from chunking.chunk import Chunk
from retrieval.bm25_store import BM25Store
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.pipeline import (
    STAGE_ORDER,
    PipelineStage,
    fill_skipped,
)
from retrieval.ranking import RetrievalResult, RetrievalTrace, StageScore


def _chunk(cid: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=cid, document_id="doc", text=text, start_char=0, end_char=len(text)
    )


CHUNKS = [
    _chunk("a", "acid transactions durability guarantee"),
    _chunk("b", "quokka quokka quokka"),
    _chunk("c", "vector space embeddings similarity"),
]


class FakeDense:
    def __init__(self, embedding_ms: float = 0.5):
        self.embedding_ms = embedding_ms
        self.last_top_k: int | None = None

    def retrieve(self, query: str, top_k: int) -> List[RetrievalResult]:
        results, _ = self.retrieve_traced(query, top_k)
        return results

    def retrieve_traced(self, query: str, top_k: int):
        self.last_top_k = top_k
        results = [
            RetrievalResult(
                chunk=c,
                score=0.9 - 0.1 * i,
                rank=i + 1,
                trace=RetrievalTrace(dense=StageScore(score=0.9 - 0.1 * i, rank=i + 1)),
            )
            for i, c in enumerate(CHUNKS[:top_k])
        ]
        return results, [
            PipelineStage(name="embedding", status="ok", latency_ms=self.embedding_ms),
            PipelineStage(
                name="dense",
                status="ok",
                latency_ms=0.3,
                candidates_in=len(CHUNKS),
                candidates_out=len(results),
            ),
        ]


def build() -> HybridRetriever:
    return HybridRetriever(dense=FakeDense(), bm25=BM25Store(CHUNKS))


def names(stages: List[PipelineStage]) -> List[str]:
    return [s.name for s in stages]


def by_name(stages: List[PipelineStage]) -> dict:
    return {s.name: s for s in stages}


class TestFillSkipped:
    def test_every_stage_appears_even_when_unreported(self):
        # A stage that vanishes from the diagram reads as "this deployment has
        # no reranker" rather than "the reranker did not run for this query".
        filled = fill_skipped(
            [PipelineStage(name="dense", status="ok", latency_ms=1.0)]
        )
        assert names(filled) == list(STAGE_ORDER)

    def test_unreported_stages_are_marked_skipped(self):
        filled = by_name(
            fill_skipped([PipelineStage(name="dense", status="ok", latency_ms=1.0)])
        )
        assert filled["reranker"].status == "skipped"
        assert filled["dense"].status == "ok"

    def test_reported_stages_are_left_alone(self):
        stage = PipelineStage(
            name="dense",
            status="ok",
            latency_ms=4.2,
            candidates_in=19,
            candidates_out=5,
        )
        assert by_name(fill_skipped([stage]))["dense"] is stage

    def test_a_skipped_stage_has_no_latency(self):
        # Zero because nothing was measured. The UI must not draw it on the same
        # scale as a stage that genuinely took 0.4 ms.
        assert PipelineStage.skipped("reranker").latency_ms == 0.0

    def test_a_skipped_stage_has_no_candidate_counts(self):
        skipped = PipelineStage.skipped("reranker")
        assert skipped.candidates_in is None
        assert skipped.candidates_out is None

    def test_order_is_the_data_flow(self):
        assert STAGE_ORDER == (
            "embedding",
            "dense",
            "sparse",
            "fusion",
            "reranker",
            "generation",
        )


class TestHybridStages:
    def test_reports_the_four_stages_it_runs(self):
        _, stages = build().retrieve_traced("acid", top_k=2)
        assert names(stages) == ["embedding", "dense", "sparse", "fusion"]

    def test_every_reported_stage_ran(self):
        _, stages = build().retrieve_traced("acid", top_k=2)
        assert all(s.status == "ok" for s in stages)

    def test_dense_reports_the_corpus_it_searched(self):
        _, stages = build().retrieve_traced("acid", top_k=2)
        assert by_name(stages)["dense"].candidates_in == len(CHUNKS)

    def test_fusion_counts_the_union_not_the_sum(self):
        # A chunk both retrievers found is one candidate. Adding the two lists
        # would overstate the funnel entering fusion.
        results, stages = build().retrieve_traced("acid durability", top_k=3)
        fusion = by_name(stages)["fusion"]
        assert fusion.candidates_in <= len(CHUNKS)
        assert fusion.candidates_out == len(results)

    def test_embedding_has_no_candidate_counts(self):
        # A question is not a candidate set; "1 → 1" would be noise.
        _, stages = build().retrieve_traced("acid", top_k=2)
        embedding = by_name(stages)["embedding"]
        assert embedding.candidates_in is None
        assert embedding.candidates_out is None

    def test_latencies_are_measured_separately(self):
        # One "retrieval" number hides which stage a slow query waited on.
        _, stages = build().retrieve_traced("acid", top_k=2)
        assert by_name(stages)["embedding"].latency_ms > 0
        assert by_name(stages)["fusion"].latency_ms >= 0


class TestSingleStageModes:
    def test_a_sparse_query_genuinely_skips_embedding(self):
        # BM25 matches terms; nothing is embedded. This is the one stage the
        # live pipeline skips by request rather than by configuration.
        _, stages = build().retrieve_traced("quokka", top_k=2, mode="sparse")
        assert by_name(stages)["embedding"].status == "skipped"
        assert by_name(stages)["sparse"].status == "ok"

    def test_a_sparse_query_does_not_report_dense_or_fusion(self):
        _, stages = build().retrieve_traced("quokka", top_k=2, mode="sparse")
        assert "dense" not in names(stages)
        assert "fusion" not in names(stages)

    def test_a_dense_query_embeds(self):
        _, stages = build().retrieve_traced("vector", top_k=2, mode="dense")
        assert by_name(stages)["embedding"].status == "ok"

    def test_a_dense_query_does_not_report_sparse_or_fusion(self):
        # Nothing was fused, so reporting a fusion stage would be a fiction.
        _, stages = build().retrieve_traced("vector", top_k=2, mode="dense")
        assert "sparse" not in names(stages)
        assert "fusion" not in names(stages)

    @pytest.mark.parametrize("mode", ["hybrid", "dense", "sparse"])
    def test_the_reranker_is_never_reported_because_it_is_not_wired(self, mode):
        _, stages = build().retrieve_traced("acid", top_k=2, mode=mode)
        assert "reranker" not in names(stages)

    @pytest.mark.parametrize("mode", ["hybrid", "dense", "sparse"])
    def test_filling_makes_every_mode_render_the_whole_diagram(self, mode):
        _, stages = build().retrieve_traced("acid", top_k=2, mode=mode)
        assert names(fill_skipped(stages)) == list(STAGE_ORDER)
