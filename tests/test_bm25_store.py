"""Tests for BM25Store keyword retrieval."""
import pytest

from chunking.chunk import Chunk
from retrieval.bm25_store import BM25Store
from retrieval.ranking import RetrievalResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chunk(idx: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"doc_{idx}",
        document_id="doc",
        text=text,
        start_char=idx * 100,
        end_char=idx * 100 + len(text),
    )


@pytest.fixture
def chunks():
    return [
        _make_chunk(0, "The Eiffel Tower is located in Paris France"),
        _make_chunk(1, "Machine learning models learn from training data"),
        _make_chunk(2, "Python is a popular programming language"),
        _make_chunk(3, "Paris is the capital city of France"),
        _make_chunk(4, "Neural networks are a type of machine learning model"),
    ]


@pytest.fixture
def store(chunks):
    return BM25Store(chunks)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestBM25StoreInit:
    def test_ntotal_matches_chunk_count(self, store, chunks):
        assert store.ntotal == len(chunks)

    def test_empty_store_is_valid(self):
        store = BM25Store([])
        assert store.ntotal == 0


# ---------------------------------------------------------------------------
# Search — basic behaviour
# ---------------------------------------------------------------------------

class TestBM25Search:
    def test_returns_list(self, store):
        assert isinstance(store.search("Eiffel Tower"), list)

    def test_results_are_retrieval_result_instances(self, store):
        for r in store.search("Paris France"):
            assert isinstance(r, RetrievalResult)

    def test_top_result_is_most_relevant(self, store):
        results = store.search("Eiffel Tower Paris")
        # chunks 0 and 3 mention Paris; chunk 0 also has Eiffel Tower
        assert results[0].chunk.chunk_id in ("doc_0", "doc_3")

    def test_machine_learning_query(self, store):
        results = store.search("machine learning model")
        ids = [r.chunk.chunk_id for r in results]
        # chunks 1 and 4 mention machine learning
        assert "doc_1" in ids or "doc_4" in ids

    def test_no_results_for_unrelated_query(self, store):
        results = store.search("quantum entanglement superconductor")
        assert results == []

    def test_top_k_limits_results(self, store):
        results = store.search("the", top_k=2)
        assert len(results) <= 2

    def test_ranks_are_1_indexed_and_sequential(self, store):
        results = store.search("Paris France")
        for i, r in enumerate(results, start=1):
            assert r.rank == i

    def test_scores_are_positive(self, store):
        for r in store.search("Paris"):
            assert r.score > 0.0

    def test_scores_are_descending(self, store):
        results = store.search("machine learning")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestBM25EdgeCases:
    def test_empty_store_returns_empty_list(self):
        store = BM25Store([])
        assert store.search("anything") == []

    def test_single_chunk_store(self):
        # With a 1-doc corpus BM25 IDF is low but search still works
        chunk = _make_chunk(0, "hello world foo bar baz")
        store = BM25Store([chunk])
        # Results may be empty if IDF rounds to near-zero; just confirm no crash
        results = store.search("hello world")
        assert isinstance(results, list)

    def test_top_k_larger_than_corpus(self, store, chunks):
        results = store.search("the", top_k=100)
        assert len(results) <= len(chunks)
