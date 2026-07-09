"""Tests for incremental index updates (VectorStorage.append + FAISSStore.add)."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from chunking.chunk import Chunk
from embeddings.storage import VectorStorage
from retrieval.faiss_store import FAISSStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIM = 4


def _random_vectors(n: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.random((n, DIM)).astype(np.float32)


def _make_chunks(start: int, count: int) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"doc_chunk_{i}",
            document_id="doc",
            text=f"Chunk text number {i}.",
            start_char=i * 20,
            end_char=i * 20 + 20,
        )
        for i in range(start, start + count)
    ]


# ---------------------------------------------------------------------------
# FAISSStore.add — incremental vector insertion
# ---------------------------------------------------------------------------

class TestFAISSStoreAdd:
    def test_add_increases_ntotal(self):
        store = FAISSStore(dimension=DIM)
        store.add(_random_vectors(5))
        assert store.ntotal == 5

    def test_second_add_accumulates(self):
        store = FAISSStore(dimension=DIM)
        store.add(_random_vectors(5))
        store.add(_random_vectors(3))
        assert store.ntotal == 8

    def test_search_finds_appended_vectors(self):
        store = FAISSStore(dimension=DIM)
        v_first = _random_vectors(3)
        store.add(v_first)

        v_new = _random_vectors(2)
        store.add(v_new)

        query = v_new[0]
        scores, indices = store.search(query, top_k=1)
        assert len(scores) == 1  # found something

    def test_add_rejects_wrong_dimension(self):
        store = FAISSStore(dimension=DIM)
        with pytest.raises(ValueError, match="Expected shape"):
            store.add(np.zeros((3, DIM + 1), dtype=np.float32))


# ---------------------------------------------------------------------------
# VectorStorage.append — combined vectors + metadata
# ---------------------------------------------------------------------------

class TestVectorStorageAppend:
    @pytest.fixture
    def storage(self, tmp_path):
        return VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )

    def test_append_to_existing_index(self, storage):
        vecs = _random_vectors(3)
        chunks = _make_chunks(0, 3)
        storage.save(vecs, chunks)

        new_vecs = _random_vectors(2)
        new_chunks = _make_chunks(3, 2)
        storage.append(new_vecs, new_chunks)

        loaded_vecs, loaded_records = storage.load()
        assert loaded_vecs.shape[0] == 5
        assert len(loaded_records) == 5

    def test_appended_chunk_ids_preserved(self, storage):
        storage.save(_random_vectors(2), _make_chunks(0, 2))
        storage.append(_random_vectors(1), _make_chunks(2, 1))

        _, records = storage.load()
        ids = [r["chunk_id"] for r in records]
        assert "doc_chunk_2" in ids

    def test_original_chunks_unchanged_after_append(self, storage):
        orig_chunks = _make_chunks(0, 3)
        storage.save(_random_vectors(3), orig_chunks)
        storage.append(_random_vectors(2), _make_chunks(3, 2))

        _, records = storage.load()
        orig_ids = {c.chunk_id for c in orig_chunks}
        stored_ids = {r["chunk_id"] for r in records[:3]}
        assert orig_ids == stored_ids

    def test_append_mismatch_raises_value_error(self, storage):
        storage.save(_random_vectors(2), _make_chunks(0, 2))
        with pytest.raises(ValueError, match="Length mismatch"):
            storage.append(_random_vectors(3), _make_chunks(2, 1))

    def test_append_to_nonexistent_raises_file_not_found(self, storage):
        with pytest.raises(FileNotFoundError):
            storage.append(_random_vectors(1), _make_chunks(0, 1))
