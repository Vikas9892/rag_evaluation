"""Unit tests for Phase 3 — embedding pipeline."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chunking.chunk import Chunk
from embeddings.embedder import Embedder
from embeddings.service import EmbeddingService
from embeddings.storage import VectorStorage


# ---------------------------------------------------------------------------
# Session-scoped fixtures — model loads once for the entire test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def embedder() -> Embedder:
    return Embedder()


@pytest.fixture(scope="session")
def service(embedder: Embedder) -> EmbeddingService:
    return EmbeddingService(embedder=embedder)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def make_chunk(idx: int, text: str = "") -> Chunk:
    body = text or f"This is test chunk number {idx} describing a technical concept."
    return Chunk(
        chunk_id=f"doc.txt_chunk_{idx:04d}",
        document_id="doc.txt",
        text=body,
        start_char=idx * 60,
        end_char=idx * 60 + len(body),
        metadata={"source": "doc.txt", "chunk_index": idx, "strategy": "recursive"},
    )


# ---------------------------------------------------------------------------
# Embedder — shape and dtype
# ---------------------------------------------------------------------------

class TestEmbedderShape:
    def test_embed_returns_1d_array(self, embedder):
        v = embedder.embed("Hello world")
        assert v.ndim == 1

    def test_embed_returns_correct_dimension(self, embedder):
        v = embedder.embed("Hello world")
        assert v.shape == (embedder.dimension,)

    def test_embed_dtype_is_float32(self, embedder):
        v = embedder.embed("Hello world")
        assert v.dtype == np.float32

    def test_embed_many_returns_2d_array(self, embedder):
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        vecs = embedder.embed_many(texts)
        assert vecs.ndim == 2

    def test_embed_many_correct_shape(self, embedder):
        texts = ["a", "b", "c", "d", "e"]
        vecs = embedder.embed_many(texts)
        assert vecs.shape == (5, embedder.dimension)

    def test_embed_many_single_text_shape(self, embedder):
        vecs = embedder.embed_many(["only one"])
        assert vecs.shape == (1, embedder.dimension)

    def test_embed_many_empty_list_returns_empty(self, embedder):
        vecs = embedder.embed_many([])
        assert vecs.shape == (0, embedder.dimension)

    def test_dimension_attribute_matches_output(self, embedder):
        v = embedder.embed("test")
        assert len(v) == embedder.dimension


# ---------------------------------------------------------------------------
# Embedder — semantic correctness
# ---------------------------------------------------------------------------

class TestEmbedderSemantics:
    def test_embed_is_deterministic(self, embedder):
        text = "Deadlock occurs when processes are unable to proceed."
        v1 = embedder.embed(text)
        v2 = embedder.embed(text)
        np.testing.assert_array_equal(v1, v2)

    def test_embed_many_is_deterministic(self, embedder):
        texts = ["CPU scheduling", "Memory management", "File systems"]
        v1 = embedder.embed_many(texts)
        v2 = embedder.embed_many(texts)
        np.testing.assert_array_equal(v1, v2)

    def test_different_texts_produce_different_vectors(self, embedder):
        v_cs = embedder.embed("CPU scheduling algorithm")
        v_db = embedder.embed("Relational database normalization")
        assert not np.allclose(v_cs, v_db)

    def test_similar_texts_have_higher_cosine_sim_than_dissimilar(self, embedder):
        v_a = embedder.embed("The CPU scheduler selects processes for execution.")
        v_b = embedder.embed("Process scheduling decides which process runs on the CPU.")
        v_c = embedder.embed("A banana is a tropical fruit with yellow skin.")
        assert cosine_sim(v_a, v_b) > cosine_sim(v_a, v_c)

    def test_embed_many_single_matches_embed(self, embedder):
        text = "Testing batch consistency"
        single = embedder.embed(text)
        batch = embedder.embed_many([text])
        np.testing.assert_allclose(batch[0], single, rtol=1e-5)

    def test_embed_empty_string_does_not_crash(self, embedder):
        v = embedder.embed("")
        assert v.shape == (embedder.dimension,)


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------

class TestEmbeddingService:
    def test_embed_chunks_correct_shape(self, service):
        chunks = [make_chunk(i) for i in range(5)]
        vecs = service.embed_chunks(chunks)
        assert vecs.shape == (5, service.embedder.dimension)

    def test_embed_chunks_empty_returns_empty(self, service):
        vecs = service.embed_chunks([])
        assert vecs.shape == (0, service.embedder.dimension)

    def test_embed_chunks_single_chunk(self, service):
        vecs = service.embed_chunks([make_chunk(0)])
        assert vecs.shape == (1, service.embedder.dimension)

    def test_embed_chunks_preserves_row_order(self, service):
        texts = [
            "Operating system manages hardware resources.",
            "Database uses B-trees for indexing.",
            "Network protocols define communication rules.",
        ]
        chunks = [make_chunk(i, text=t) for i, t in enumerate(texts)]
        vecs = service.embed_chunks(chunks)
        direct = service.embedder.embed_many(texts)
        np.testing.assert_allclose(vecs, direct, rtol=1e-5)

    def test_embed_chunks_dtype_float32(self, service):
        vecs = service.embed_chunks([make_chunk(0)])
        assert vecs.dtype == np.float32

    def test_service_uses_injected_embedder(self, embedder):
        svc = EmbeddingService(embedder=embedder)
        assert svc.embedder is embedder


# ---------------------------------------------------------------------------
# VectorStorage
# ---------------------------------------------------------------------------

class TestVectorStorage:
    def _make_vectors(self, n: int, dim: int = 384) -> np.ndarray:
        rng = np.random.default_rng(42)
        return rng.random((n, dim), dtype=np.float32).astype(np.float32)

    def _make_chunks(self, n: int) -> list:
        return [make_chunk(i) for i in range(n)]

    def test_save_then_load_vectors_are_equal(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        vecs = self._make_vectors(4)
        chunks = self._make_chunks(4)
        storage.save(vecs, chunks)
        loaded_vecs, _ = storage.load()
        np.testing.assert_array_equal(vecs, loaded_vecs)

    def test_save_then_load_metadata_count_matches(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        chunks = self._make_chunks(6)
        storage.save(self._make_vectors(6), chunks)
        _, records = storage.load()
        assert len(records) == 6

    def test_metadata_records_have_required_keys(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        chunks = self._make_chunks(3)
        storage.save(self._make_vectors(3), chunks)
        _, records = storage.load()
        required = {"chunk_id", "document_id", "text", "start_char", "end_char", "metadata"}
        for rec in records:
            assert required.issubset(rec.keys())

    def test_metadata_chunk_id_matches_original(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        chunks = self._make_chunks(3)
        storage.save(self._make_vectors(3), chunks)
        _, records = storage.load()
        for chunk, rec in zip(chunks, records):
            assert rec["chunk_id"] == chunk.chunk_id

    def test_metadata_text_matches_original(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        chunks = self._make_chunks(3)
        storage.save(self._make_vectors(3), chunks)
        _, records = storage.load()
        for chunk, rec in zip(chunks, records):
            assert rec["text"] == chunk.text

    def test_save_creates_missing_parent_directory(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "index"
        storage = VectorStorage(
            vectors_path=nested / "vectors.npy",
            metadata_path=nested / "metadata.json",
        )
        storage.save(self._make_vectors(2), self._make_chunks(2))
        assert (nested / "vectors.npy").exists()
        assert (nested / "metadata.json").exists()

    def test_load_missing_vectors_raises(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "nope.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        with pytest.raises(FileNotFoundError, match="Vectors file not found"):
            storage.load()

    def test_load_missing_metadata_raises(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "nope.json",
        )
        # create the vectors file so we hit the metadata check
        np.save(str(tmp_path / "vectors.npy"), self._make_vectors(1))
        with pytest.raises(FileNotFoundError, match="Metadata file not found"):
            storage.load()

    def test_save_length_mismatch_raises(self, tmp_path):
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        with pytest.raises(ValueError, match="Length mismatch"):
            storage.save(self._make_vectors(5), self._make_chunks(3))

    def test_vectors_are_index_aligned_with_metadata(self, tmp_path):
        """After save+load, row i must correspond to record i."""
        storage = VectorStorage(
            vectors_path=tmp_path / "vectors.npy",
            metadata_path=tmp_path / "metadata.json",
        )
        chunks = self._make_chunks(4)
        vecs = self._make_vectors(4)
        storage.save(vecs, chunks)
        loaded_vecs, records = storage.load()
        for i, (chunk, rec) in enumerate(zip(chunks, records)):
            assert rec["chunk_id"] == chunk.chunk_id
            np.testing.assert_array_equal(loaded_vecs[i], vecs[i])
