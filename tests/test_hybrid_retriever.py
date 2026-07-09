"""Tests for HybridRetriever — RRF fusion of dense + sparse scores."""
from typing import List
from unittest.mock import MagicMock

import pytest

from chunking.chunk import Chunk
from retrieval.bm25_store import BM25Store
from retrieval.hybrid_retriever import HybridRetriever, _RRF_K
from retrieval.ranking import RetrievalResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chunk(idx: int, text: str = "text") -> Chunk:
    return Chunk(
        chunk_id=f"chunk_{idx}",
        document_id="doc",
        text=text,
        start_char=0,
        end_char=len(text),
    )


def _result(chunk: Chunk, score: float, rank: int) -> RetrievalResult:
    return RetrievalResult(chunk=chunk, score=score, rank=rank)


def _make_hybrid(dense_results: List[RetrievalResult], bm25_results: List[RetrievalResult]) -> HybridRetriever:
    dense_mock = MagicMock()
    dense_mock.retrieve.return_value = dense_results
    dense_mock._store.ntotal = len(dense_results)

    chunks = [r.chunk for r in bm25_results]
    bm25_mock = MagicMock(spec=BM25Store)
    bm25_mock.search.return_value = bm25_results
    bm25_mock.ntotal = len(chunks)

    return HybridRetriever(dense=dense_mock, bm25=bm25_mock)


# ---------------------------------------------------------------------------
# RRF fusion correctness
# ---------------------------------------------------------------------------

class TestRRFFusion:
    def test_chunk_in_both_retrievers_scores_higher(self):
        c_shared = _chunk(0, "shared chunk")
        c_dense_only = _chunk(1, "dense only")
        c_bm25_only = _chunk(2, "bm25 only")

        hybrid = _make_hybrid(
            dense_results=[_result(c_shared, 0.9, 1), _result(c_dense_only, 0.8, 2)],
            bm25_results=[_result(c_shared, 5.0, 1), _result(c_bm25_only, 3.0, 2)],
        )
        results = hybrid.retrieve("query", top_k=3)

        ids = [r.chunk.chunk_id for r in results]
        assert ids[0] == "chunk_0"  # shared chunk must be first

    def test_rrf_score_formula(self):
        """Verify the score equals 1/(k+rank) for a rank-1 result from one retriever."""
        c = _chunk(0)
        hybrid = _make_hybrid(
            dense_results=[_result(c, 1.0, 1)],
            bm25_results=[],
        )
        results = hybrid.retrieve("q", top_k=1)
        expected = round(1.0 / (_RRF_K + 1), 6)
        assert abs(results[0].score - expected) < 1e-5

    def test_ranks_are_1_indexed(self):
        chunks = [_chunk(i) for i in range(3)]
        hybrid = _make_hybrid(
            dense_results=[_result(c, 1.0 - i * 0.1, i + 1) for i, c in enumerate(chunks)],
            bm25_results=[],
        )
        results = hybrid.retrieve("q", top_k=3)
        assert [r.rank for r in results] == [1, 2, 3]

    def test_top_k_limits_output(self):
        chunks = [_chunk(i) for i in range(10)]
        hybrid = _make_hybrid(
            dense_results=[_result(c, 1.0 - i * 0.05, i + 1) for i, c in enumerate(chunks)],
            bm25_results=[],
        )
        assert len(hybrid.retrieve("q", top_k=3)) == 3

    def test_empty_both_retrievers_returns_empty(self):
        hybrid = _make_hybrid(dense_results=[], bm25_results=[])
        assert hybrid.retrieve("q") == []

    def test_scores_are_descending(self):
        chunks = [_chunk(i, f"text about topic {i}") for i in range(4)]
        hybrid = _make_hybrid(
            dense_results=[_result(c, 0.9 - i * 0.1, i + 1) for i, c in enumerate(chunks)],
            bm25_results=[_result(chunks[2], 3.0, 1), _result(chunks[3], 2.0, 2)],
        )
        results = hybrid.retrieve("q", top_k=4)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_no_duplicate_chunk_ids_in_results(self):
        c = _chunk(0, "both retrievers return this chunk")
        hybrid = _make_hybrid(
            dense_results=[_result(c, 0.9, 1)],
            bm25_results=[_result(c, 5.0, 1)],
        )
        results = hybrid.retrieve("q", top_k=5)
        chunk_ids = [r.chunk.chunk_id for r in results]
        assert len(chunk_ids) == len(set(chunk_ids))
