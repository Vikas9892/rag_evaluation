"""Unit tests for Phase 4 — FAISS retrieval pipeline."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chunking.chunk import Chunk
from retrieval.faiss_store import FAISSStore
from retrieval.ranking import RetrievalResult
from retrieval.retriever import Retriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(0)


def rand_vecs(n: int, dim: int = 8) -> np.ndarray:
    return RNG.random((n, dim), dtype=np.float64).astype(np.float32)


def unit_vec(dim: int = 8) -> np.ndarray:
    v = RNG.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def make_metadata(n: int) -> list:
    return [
        {
            "chunk_id": f"doc.txt_chunk_{i:04d}",
            "document_id": "doc.txt",
            "text": f"Chunk {i}: This explains concept number {i} in detail.",
            "start_char": i * 60,
            "end_char": i * 60 + 50,
            "metadata": {"source": "doc.txt", "chunk_index": i},
        }
        for i in range(n)
    ]


class MockEmbedder:
    """Returns a fixed pre-defined vector so retriever tests are deterministic."""

    dimension = 8

    def __init__(self, vector: np.ndarray | None = None) -> None:
        self._vector = vector if vector is not None else unit_vec()

    def embed(self, text: str) -> np.ndarray:  # noqa: ARG002
        return self._vector


# ---------------------------------------------------------------------------
# RetrievalResult
# ---------------------------------------------------------------------------

class TestRetrievalResult:
    def _chunk(self) -> Chunk:
        return Chunk(
            chunk_id="doc_chunk_0000",
            document_id="doc.txt",
            text="Deadlock occurs when...",
            start_char=0,
            end_char=24,
        )

    def test_fields_are_set(self):
        r = RetrievalResult(chunk=self._chunk(), score=0.92, rank=1)
        assert r.score == 0.92
        assert r.rank == 1
        assert r.chunk.chunk_id == "doc_chunk_0000"

    def test_equality(self):
        c = self._chunk()
        assert RetrievalResult(c, 0.9, 1) == RetrievalResult(c, 0.9, 1)

    def test_different_ranks_are_not_equal(self):
        c = self._chunk()
        assert RetrievalResult(c, 0.9, 1) != RetrievalResult(c, 0.9, 2)


# ---------------------------------------------------------------------------
# FAISSStore — creation and population
# ---------------------------------------------------------------------------

class TestFAISSStoreCreation:
    def test_new_store_is_empty(self):
        assert FAISSStore(8).ntotal == 0

    def test_add_increments_ntotal(self):
        store = FAISSStore(8)
        store.add(rand_vecs(5))
        assert store.ntotal == 5

    def test_add_multiple_batches_accumulates(self):
        store = FAISSStore(8)
        store.add(rand_vecs(3))
        store.add(rand_vecs(4))
        assert store.ntotal == 7

    def test_add_wrong_dimension_raises(self):
        store = FAISSStore(8)
        with pytest.raises(ValueError, match="Expected shape"):
            store.add(rand_vecs(5, dim=16))

    def test_add_1d_input_raises(self):
        store = FAISSStore(8)
        with pytest.raises(ValueError, match="Expected shape"):
            store.add(np.zeros(8, dtype=np.float32))

    def test_duplicate_vectors_stored_as_separate_entries(self):
        store = FAISSStore(8)
        v = rand_vecs(1)
        store.add(v)
        store.add(v)
        assert store.ntotal == 2


# ---------------------------------------------------------------------------
# FAISSStore — search correctness
# ---------------------------------------------------------------------------

class TestFAISSStoreSearch:
    def test_search_returns_top_k_results(self):
        store = FAISSStore(8)
        store.add(rand_vecs(10))
        scores, indices = store.search(unit_vec(), top_k=3)
        assert len(scores) == 3
        assert len(indices) == 3

    def test_search_returns_self_as_best_match(self):
        """Querying with an already-indexed vector must rank itself first."""
        store = FAISSStore(8)
        vecs = rand_vecs(10)
        store.add(vecs)
        _, indices = store.search(vecs[4], top_k=1)
        assert indices[0] == 4

    def test_scores_are_in_descending_order(self):
        store = FAISSStore(8)
        store.add(rand_vecs(20))
        scores, _ = store.search(unit_vec(), top_k=10)
        assert list(scores) == sorted(scores, reverse=True)

    def test_scores_are_valid_cosine_similarities(self):
        store = FAISSStore(8)
        store.add(rand_vecs(10))
        scores, _ = store.search(unit_vec(), top_k=5)
        assert all(-1.0 <= float(s) <= 1.0 for s in scores)

    def test_search_empty_index_returns_empty_arrays(self):
        store = FAISSStore(8)
        scores, indices = store.search(unit_vec(), top_k=5)
        assert len(scores) == 0
        assert len(indices) == 0

    def test_top_k_larger_than_index_size_returns_all(self):
        store = FAISSStore(8)
        store.add(rand_vecs(3))
        scores, indices = store.search(unit_vec(), top_k=100)
        assert len(scores) == 3
        assert len(indices) == 3

    def test_top_k_equals_one_returns_single_result(self):
        store = FAISSStore(8)
        store.add(rand_vecs(5))
        scores, indices = store.search(unit_vec(), top_k=1)
        assert len(scores) == 1

    def test_top_k_zero_raises(self):
        store = FAISSStore(8)
        store.add(rand_vecs(5))
        with pytest.raises(ValueError, match="top_k must be >= 1"):
            store.search(unit_vec(), top_k=0)

    def test_indices_are_within_valid_range(self):
        n = 10
        store = FAISSStore(8)
        store.add(rand_vecs(n))
        _, indices = store.search(unit_vec(), top_k=5)
        assert all(0 <= int(i) < n for i in indices)


# ---------------------------------------------------------------------------
# FAISSStore — persistence
# ---------------------------------------------------------------------------

class TestFAISSStorePersistence:
    def test_save_and_load_ntotal_preserved(self, tmp_path):
        store = FAISSStore(8)
        store.add(rand_vecs(7))
        p = tmp_path / "test.index"
        store.save(p)
        loaded = FAISSStore.load(p)
        assert loaded.ntotal == 7

    def test_save_and_load_dimension_preserved(self, tmp_path):
        store = FAISSStore(8)
        store.add(rand_vecs(3))
        p = tmp_path / "test.index"
        store.save(p)
        loaded = FAISSStore.load(p)
        assert loaded.dimension == 8

    def test_save_and_load_search_results_identical(self, tmp_path):
        store = FAISSStore(8)
        vecs = rand_vecs(10)
        store.add(vecs)
        q = unit_vec()
        orig_scores, orig_idx = store.search(q, top_k=5)
        p = tmp_path / "test.index"
        store.save(p)
        loaded = FAISSStore.load(p)
        loaded_scores, loaded_idx = loaded.search(q, top_k=5)
        np.testing.assert_array_equal(orig_idx, loaded_idx)
        np.testing.assert_allclose(orig_scores, loaded_scores, rtol=1e-5)

    def test_save_creates_missing_parent_directory(self, tmp_path):
        store = FAISSStore(8)
        store.add(rand_vecs(2))
        p = tmp_path / "deep" / "nested" / "test.index"
        store.save(p)
        assert p.exists()

    def test_load_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="FAISS index not found"):
            FAISSStore.load(tmp_path / "ghost.index")


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

class TestRetriever:
    def _build(self, n: int = 8) -> tuple:
        """Return (Retriever, metadata_list) backed by random vectors."""
        metadata = make_metadata(n)
        vecs = rand_vecs(n)
        store = FAISSStore(8)
        store.add(vecs)
        query_vec = vecs[0].copy()  # known vector → rank 0 must map to metadata[0]
        embedder = MockEmbedder(vector=query_vec)
        retriever = Retriever(store=store, metadata=metadata, embedder=embedder)
        return retriever, metadata, query_vec

    def test_retrieve_returns_retrieval_result_objects(self):
        retriever, _, _ = self._build()
        results = retriever.retrieve("any query", top_k=3)
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_retrieve_respects_top_k(self):
        retriever, _, _ = self._build(n=10)
        for k in (1, 3, 5):
            results = retriever.retrieve("query", top_k=k)
            assert len(results) == k

    def test_top_result_maps_to_correct_metadata(self):
        """MockEmbedder returns vecs[0], so the top hit must be metadata[0]."""
        retriever, metadata, _ = self._build()
        results = retriever.retrieve("query", top_k=1)
        assert results[0].chunk.chunk_id == metadata[0]["chunk_id"]

    def test_chunk_fields_match_metadata_record(self):
        retriever, metadata, _ = self._build()
        results = retriever.retrieve("query", top_k=3)
        for result in results:
            rec = next(m for m in metadata if m["chunk_id"] == result.chunk.chunk_id)
            assert result.chunk.document_id == rec["document_id"]
            assert result.chunk.text == rec["text"]
            assert result.chunk.start_char == rec["start_char"]
            assert result.chunk.end_char == rec["end_char"]

    def test_results_ordered_by_score_descending(self):
        retriever, _, _ = self._build(n=10)
        results = retriever.retrieve("query", top_k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_are_1_indexed_and_sequential(self):
        retriever, _, _ = self._build(n=8)
        results = retriever.retrieve("query", top_k=4)
        assert [r.rank for r in results] == list(range(1, len(results) + 1))

    def test_scores_are_valid_cosine_similarities(self):
        retriever, _, _ = self._build()
        for result in retriever.retrieve("query", top_k=5):
            assert -1.0 <= result.score <= 1.0

    def test_top_k_larger_than_index_returns_all(self):
        retriever, _, _ = self._build(n=4)
        results = retriever.retrieve("query", top_k=100)
        assert len(results) == 4

    def test_retriever_uses_injected_embedder(self):
        vecs = rand_vecs(5)
        store = FAISSStore(8)
        store.add(vecs)
        embedder = MockEmbedder(vector=vecs[2].copy())
        retriever = Retriever(store=store, metadata=make_metadata(5), embedder=embedder)
        results = retriever.retrieve("anything", top_k=1)
        assert results[0].chunk.chunk_id == make_metadata(5)[2]["chunk_id"]

    def test_retriever_from_disk(self, tmp_path):
        """End-to-end: save index + metadata -> load via from_disk -> retrieve."""
        import json
        from embeddings.storage import VectorStorage

        vecs = rand_vecs(6)
        metadata = make_metadata(6)

        # Persist using VectorStorage so the alignment invariant holds
        from chunking.chunk import Chunk as _Chunk

        chunks = [
            _Chunk(
                chunk_id=m["chunk_id"],
                document_id=m["document_id"],
                text=m["text"],
                start_char=m["start_char"],
                end_char=m["end_char"],
                metadata=m["metadata"],
            )
            for m in metadata
        ]
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        storage.save(vecs, chunks)

        index_path = tmp_path / "faiss.index"
        store = FAISSStore(8)
        store.add(vecs)
        store.save(index_path)

        embedder = MockEmbedder(vector=vecs[1].copy())
        retriever = Retriever.from_disk(
            index_path=index_path,
            metadata_path=tmp_path / "metadata.json",
            embedder=embedder,
        )
        results = retriever.retrieve("test", top_k=1)
        assert results[0].chunk.chunk_id == metadata[1]["chunk_id"]
