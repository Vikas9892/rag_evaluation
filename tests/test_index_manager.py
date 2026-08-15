"""Tests for removing a document from a built corpus.

The point of these is that deletion is real. FAISS has no delete, so the index
is rebuilt from the vectors already on disk — which costs no embedding, and is
why the API no longer has to tell users their chunks are still searchable.
"""

import json

import numpy as np
import pytest

from corpora import corpus_layout, remove_document
from corpora.index_manager import chunk_count
from retrieval.faiss_store import FAISSStore


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr("corpora.layout.CORPORA_DIR", tmp_path / "corpora")
    return "notes"


def build(corpus_id: str, documents: dict[str, int], dim: int = 8) -> None:
    """Write a corpus containing `documents` mapped to a chunk count each."""
    layout = corpus_layout(corpus_id)
    layout.root.mkdir(parents=True, exist_ok=True)

    records, rows = [], []
    rng = np.random.default_rng(0)
    for doc_id, count in documents.items():
        for i in range(count):
            records.append(
                {
                    "chunk_id": f"{doc_id}_chunk_{i:04d}",
                    "document_id": f"{doc_id}.md",
                    "corpus_id": corpus_id,
                    "text": f"text {doc_id} {i}",
                    "start_char": 0,
                    "end_char": 10,
                    # The upload's generated id lives here; the top-level
                    # document_id is the filename a citation shows.
                    "metadata": {"document_id": doc_id},
                }
            )
            rows.append(rng.random(dim, dtype=np.float32))

    vectors = np.vstack(rows).astype(np.float32)
    np.save(str(layout.vectors_path), vectors)
    layout.metadata_path.write_text(json.dumps(records), encoding="utf-8")
    store = FAISSStore(dimension=dim)
    store.add(vectors)
    store.save(layout.faiss_path)


class TestRemoval:
    def test_removes_only_the_named_document(self, corpus):
        build(corpus, {"keep": 3, "drop": 2})
        result = remove_document(corpus, "drop")

        assert result.removed_chunks == 2
        assert result.remaining_chunks == 3

    def test_the_remaining_chunks_are_the_right_ones(self, corpus):
        build(corpus, {"keep": 3, "drop": 2})
        remove_document(corpus, "drop")

        records = json.loads(corpus_layout(corpus).metadata_path.read_text("utf-8"))
        assert {r["metadata"]["document_id"] for r in records} == {"keep"}

    def test_vectors_stay_aligned_with_metadata(self, corpus):
        # A misalignment would pair the wrong vector with the wrong chunk and
        # return confidently wrong citations.
        build(corpus, {"keep": 3, "drop": 2})
        remove_document(corpus, "drop")

        layout = corpus_layout(corpus)
        records = json.loads(layout.metadata_path.read_text("utf-8"))
        vectors = np.load(layout.vectors_path)
        assert len(records) == vectors.shape[0]

    def test_the_faiss_index_shrinks_too(self, corpus):
        # Rebuilt rather than tombstoned: a tombstoned vector would still take a
        # top-K slot and silently shorten every result list.
        build(corpus, {"keep": 3, "drop": 2})
        remove_document(corpus, "drop")

        assert FAISSStore.load(corpus_layout(corpus).faiss_path).ntotal == 3

    def test_removing_the_last_document_deletes_the_corpus(self, corpus):
        # An empty index is not queryable; leaving one would advertise a corpus
        # with no content.
        build(corpus, {"only": 2})
        result = remove_document(corpus, "only")

        assert result.corpus_deleted is True
        assert not corpus_layout(corpus).exists

    def test_removing_an_unknown_document_changes_nothing(self, corpus):
        build(corpus, {"keep": 3})
        result = remove_document(corpus, "never-here")

        assert result.removed_chunks == 0
        assert result.remaining_chunks == 3
        assert corpus_layout(corpus).exists

    def test_removing_from_a_corpus_that_was_never_indexed_is_a_no_op(self, corpus):
        result = remove_document(corpus, "anything")
        assert result == type(result)(0, 0, corpus_deleted=False)

    def test_refuses_an_inconsistent_corpus(self, corpus):
        # Filtering a corpus whose files disagree would pair the wrong vector
        # with the wrong chunk. Better to refuse and say so.
        build(corpus, {"a": 2, "b": 2})
        layout = corpus_layout(corpus)
        records = json.loads(layout.metadata_path.read_text("utf-8"))
        layout.metadata_path.write_text(json.dumps(records[:-1]), encoding="utf-8")

        with pytest.raises(ValueError, match="inconsistent"):
            remove_document(corpus, "a")

    def test_two_documents_sharing_a_filename_are_removed_separately(self, corpus):
        # The filename is what a citation shows and is not unique; the upload id
        # is what identifies the document.
        build(corpus, {"first": 2, "second": 2})
        layout = corpus_layout(corpus)
        records = json.loads(layout.metadata_path.read_text("utf-8"))
        for r in records:
            r["document_id"] = "same-name.md"
        layout.metadata_path.write_text(json.dumps(records), encoding="utf-8")

        remove_document(corpus, "first")

        remaining = json.loads(layout.metadata_path.read_text("utf-8"))
        assert {r["metadata"]["document_id"] for r in remaining} == {"second"}


class TestChunkCount:
    def test_counts_what_is_indexed(self, corpus):
        build(corpus, {"a": 3, "b": 2})
        assert chunk_count(corpus) == 5

    def test_an_unindexed_corpus_has_no_chunks(self, corpus):
        assert chunk_count(corpus) == 0
