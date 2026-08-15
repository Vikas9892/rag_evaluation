"""Tests for per-stage retrieval attribution.

Fusion used to collapse two rankings into one number and discard the inputs,
which made the retrieval table impossible to build: you could see that a chunk
came first overall but not which retriever put it there. These tests pin what
each stage now records, and — more importantly — what a missing stage means.
"""

from typing import List

import pytest

from chunking.chunk import Chunk
from retrieval.bm25_store import BM25Store
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.ranking import RetrievalResult, RetrievalTrace, StageScore


def _chunk(cid: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=cid,
        document_id="doc",
        text=text,
        start_char=0,
        end_char=len(text),
    )


class FakeDense:
    """Stands in for the FAISS-backed retriever, returning a fixed ranking."""

    def __init__(self, chunks: List[Chunk], scores: List[float] | None = None):
        self.chunks = chunks
        self.scores = scores or [0.9 - 0.1 * i for i in range(len(chunks))]
        self.last_top_k: int | None = None

    def retrieve(self, query: str, top_k: int) -> List[RetrievalResult]:
        self.last_top_k = top_k
        return [
            RetrievalResult(
                chunk=c,
                score=self.scores[i],
                rank=i + 1,
                trace=RetrievalTrace(dense=StageScore(score=self.scores[i], rank=i + 1)),
            )
            for i, c in enumerate(self.chunks[:top_k])
        ]


DENSE_ONLY = _chunk("only_dense", "vector space embeddings similarity")
SHARED = _chunk("shared", "acid transactions durability guarantee")
SPARSE_ONLY = _chunk("only_sparse", "quokka quokka quokka")


def build_hybrid() -> HybridRetriever:
    # BM25 sees all three; dense is told about two, so `only_sparse` can only
    # arrive through the sparse stage and `only_dense` only through dense.
    bm25 = BM25Store([SHARED, SPARSE_ONLY, DENSE_ONLY])
    dense = FakeDense([DENSE_ONLY, SHARED])
    return HybridRetriever(dense=dense, bm25=bm25)


def by_id(results: List[RetrievalResult]) -> dict:
    return {r.chunk.chunk_id: r for r in results}


class TestHybridTrace:
    def test_a_chunk_found_by_both_records_both(self):
        results = by_id(build_hybrid().retrieve("acid durability", top_k=5))
        trace = results["shared"].trace
        assert trace.dense is not None
        assert trace.sparse is not None

    def test_each_stage_records_its_own_rank(self):
        # The scores are in incomparable units, so the rank is what makes the
        # table readable: dense put this first, sparse put it further down.
        results = by_id(build_hybrid().retrieve("acid durability", top_k=5))
        trace = results["shared"].trace
        assert trace.dense.rank == 2
        assert trace.sparse.rank >= 1

    def test_fused_is_always_present_after_fusion(self):
        for result in build_hybrid().retrieve("acid durability", top_k=5):
            assert result.trace.fused is not None

    def test_fused_score_and_rank_match_the_final_result(self):
        for result in build_hybrid().retrieve("acid durability", top_k=5):
            assert result.trace.fused.score == pytest.approx(result.score)
            assert result.trace.fused.rank == result.rank

    def test_a_chunk_only_sparse_found_has_no_dense_stage(self):
        # Dense ran; it simply did not surface this chunk. The response reports
        # retriever="hybrid" so a reader knows the stage executed.
        results = by_id(build_hybrid().retrieve("quokka", top_k=5))
        assert "only_sparse" in results
        assert results["only_sparse"].trace.dense is None
        assert results["only_sparse"].trace.sparse is not None

    def test_a_chunk_only_dense_found_has_no_sparse_stage(self):
        # A query with no term overlap at all, so BM25 returns nothing and only
        # the dense stage can have contributed. (FakeDense ignores the query.)
        results = by_id(build_hybrid().retrieve("zzzznomatch", top_k=5))
        assert results["only_dense"].trace.sparse is None
        assert results["only_dense"].trace.dense is not None

    def test_the_reranker_stage_is_absent_because_it_does_not_run(self):
        for result in build_hybrid().retrieve("acid", top_k=5):
            assert result.trace.reranker is None

    def test_fusion_widens_the_candidate_window(self):
        # A chunk ranked low by one retriever and high by the other must still
        # be reachable, so fusion asks for more candidates than it returns.
        retriever = build_hybrid()
        retriever.retrieve("acid", top_k=3)
        assert retriever._dense.last_top_k > 3


class TestSingleStageModes:
    def test_dense_mode_records_only_the_dense_stage(self):
        results = build_hybrid().retrieve("vector embeddings", top_k=3, mode="dense")
        assert results
        for result in results:
            assert result.trace.dense is not None
            assert result.trace.sparse is None
            # Nothing was fused, so claiming a fusion score would be a fiction.
            assert result.trace.fused is None

    def test_sparse_mode_records_only_the_sparse_stage(self):
        results = build_hybrid().retrieve("quokka", top_k=3, mode="sparse")
        assert results
        for result in results:
            assert result.trace.sparse is not None
            assert result.trace.dense is None
            assert result.trace.fused is None

    def test_dense_mode_does_not_widen_the_window(self):
        # Only fusion needs extra candidates; a single stage returns what it is
        # asked for, and over-fetching would be wasted work.
        retriever = build_hybrid()
        retriever.retrieve("acid", top_k=3, mode="dense")
        assert retriever._dense.last_top_k == 3

    def test_modes_can_disagree_about_the_best_chunk(self):
        # The whole reason retriever choice is per-request: if every mode
        # returned the same ordering there would be nothing to compare.
        retriever = build_hybrid()
        dense_top = retriever.retrieve("vector embeddings", top_k=3, mode="dense")[0]
        sparse_top = retriever.retrieve("quokka", top_k=3, mode="sparse")[0]
        assert dense_top.chunk.chunk_id != sparse_top.chunk.chunk_id


class TestComponentRetrieversRecordThemselves:
    def test_bm25_records_its_own_stage(self):
        # Three documents, not two: see test_idf_is_degenerate_on_a_tiny_corpus.
        results = BM25Store([SHARED, SPARSE_ONLY, DENSE_ONLY]).search("quokka", top_k=2)
        assert results[0].trace.sparse is not None
        assert results[0].trace.sparse.score == pytest.approx(results[0].score)
        assert results[0].trace.dense is None

    def test_idf_is_degenerate_on_a_tiny_corpus(self):
        """A term in half the corpus carries no information, and BM25 says so.

        With two documents and a term in one of them, BM25's IDF floors to zero
        and the chunk is dropped as having no overlap. That is correct BM25 —
        the term does not discriminate — but at this corpus size it means the
        sparse half of hybrid retrieval is unstable in a way it would not be at
        realistic scale. Recorded here because it looks like a bug when it
        surfaces, and because it is more evidence for the corpus blocker on
        Milestone 15.
        """
        assert BM25Store([SHARED, SPARSE_ONLY]).search("quokka", top_k=2) == []
        assert BM25Store([SHARED, SPARSE_ONLY, DENSE_ONLY]).search("quokka", top_k=2)

    def test_absence_is_not_a_zero_score(self):
        # BM25 genuinely scores zero for a chunk with no term overlap. That is a
        # measurement. A missing stage is not, and the two must not collapse.
        results = build_hybrid().retrieve("quokka", top_k=5)
        traced = by_id(results)["only_sparse"].trace
        assert traced.dense is None
        assert traced.sparse.score > 0
