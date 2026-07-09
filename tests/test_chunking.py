"""Unit tests for Phase 2 — chunking pipeline."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.document import Document
from chunking.chunk import Chunk
from chunking.splitter import DocumentSplitter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_doc(text: str, doc_id: str = "test.txt") -> Document:
    return Document(id=doc_id, source=f"/raw/{doc_id}", text=text, metadata={"type": "txt", "source": doc_id})


def small_splitter(**kwargs) -> DocumentSplitter:
    """Splitter with tight settings for deterministic tests."""
    defaults = dict(chunk_size=50, chunk_overlap=10)
    defaults.update(kwargs)
    return DocumentSplitter(**defaults)


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

class TestChunk:
    def test_fields_are_set(self):
        c = Chunk(
            chunk_id="doc_chunk_0000",
            document_id="doc.txt",
            text="hello world",
            start_char=0,
            end_char=11,
            metadata={"strategy": "recursive"},
        )
        assert c.chunk_id == "doc_chunk_0000"
        assert c.document_id == "doc.txt"
        assert c.text == "hello world"
        assert c.start_char == 0
        assert c.end_char == 11

    def test_default_metadata_is_empty_dict(self):
        c = Chunk(chunk_id="x", document_id="x", text="x", start_char=0, end_char=1)
        assert c.metadata == {}

    def test_equality(self):
        c1 = Chunk(chunk_id="a", document_id="d", text="t", start_char=0, end_char=1)
        c2 = Chunk(chunk_id="a", document_id="d", text="t", start_char=0, end_char=1)
        assert c1 == c2


# ---------------------------------------------------------------------------
# Empty document
# ---------------------------------------------------------------------------

class TestEmptyDocument:
    def test_empty_text_produces_no_chunks(self):
        doc = make_doc("")
        chunks = small_splitter().split(doc)
        assert chunks == []

    def test_whitespace_only_produces_no_chunks(self):
        doc = make_doc("   \n\n   ")
        chunks = small_splitter().split(doc)
        assert chunks == []


# ---------------------------------------------------------------------------
# Small document (fits in one chunk)
# ---------------------------------------------------------------------------

class TestSmallDocument:
    def test_short_text_yields_one_chunk(self):
        doc = make_doc("Short text that fits.")
        chunks = small_splitter().split(doc)
        assert len(chunks) == 1

    def test_single_chunk_text_matches_document(self):
        text = "Short text that fits."
        doc = make_doc(text)
        chunks = small_splitter().split(doc)
        assert chunks[0].text == text

    def test_single_chunk_char_offsets(self):
        text = "Short text that fits."
        doc = make_doc(text)
        chunks = small_splitter().split(doc)
        assert chunks[0].start_char == 0
        assert chunks[0].end_char == len(text)


# ---------------------------------------------------------------------------
# Large document (multiple chunks)
# ---------------------------------------------------------------------------

class TestLargeDocument:
    def _long_text(self, sentences: int = 30) -> str:
        return " ".join(
            f"Sentence number {i} describes something important about topic {i}."
            for i in range(sentences)
        )

    def test_large_document_produces_multiple_chunks(self):
        doc = make_doc(self._long_text())
        chunks = small_splitter().split(doc)
        assert len(chunks) > 1

    def test_chunk_count_is_reasonable(self):
        text = self._long_text(60)
        doc = make_doc(text)
        splitter = DocumentSplitter(chunk_size=200, chunk_overlap=40)
        chunks = splitter.split(doc)
        # rough sanity: at least 3 chunks, not more than len(text)//50
        assert len(chunks) >= 3
        assert len(chunks) < len(text) // 50

    def test_all_chunks_are_non_empty(self):
        doc = make_doc(self._long_text())
        for chunk in small_splitter().split(doc):
            assert chunk.text.strip() != ""

    def test_chunk_size_respected(self):
        doc = make_doc(self._long_text())
        splitter = small_splitter(chunk_size=50)
        for chunk in splitter.split(doc):
            assert len(chunk.text) <= 60  # small tolerance for separator handling


# ---------------------------------------------------------------------------
# Chunk IDs and document linkage
# ---------------------------------------------------------------------------

class TestChunkIdentifiers:
    def test_chunk_ids_are_unique(self):
        doc = make_doc("word " * 200)
        chunks = small_splitter().split(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_id_contains_document_id(self):
        doc = make_doc("word " * 200, doc_id="notes.txt")
        chunks = small_splitter().split(doc)
        for chunk in chunks:
            assert chunk.chunk_id.startswith("notes.txt_chunk_")

    def test_document_id_on_every_chunk(self):
        doc = make_doc("word " * 200, doc_id="notes.txt")
        chunks = small_splitter().split(doc)
        for chunk in chunks:
            assert chunk.document_id == "notes.txt"

    def test_chunk_ids_are_zero_padded(self):
        doc = make_doc("word " * 200)
        chunks = small_splitter().split(doc)
        assert chunks[0].chunk_id.endswith("_chunk_0000")
        if len(chunks) > 1:
            assert chunks[1].chunk_id.endswith("_chunk_0001")


# ---------------------------------------------------------------------------
# Character offsets
# ---------------------------------------------------------------------------

class TestCharOffsets:
    def test_offsets_within_document_bounds(self):
        text = "word " * 200
        doc = make_doc(text)
        chunks = small_splitter().split(doc)
        for chunk in chunks:
            assert chunk.start_char >= 0
            assert chunk.end_char <= len(text)
            assert chunk.start_char < chunk.end_char

    def test_offsets_are_monotonically_increasing(self):
        doc = make_doc("word " * 200)
        chunks = small_splitter().split(doc)
        for i in range(1, len(chunks)):
            assert chunks[i].start_char >= chunks[i - 1].start_char

    def test_chunk_text_matches_offset_slice(self):
        text = "word " * 100
        doc = make_doc(text)
        chunks = small_splitter().split(doc)
        for chunk in chunks:
            assert doc.text[chunk.start_char: chunk.end_char] == chunk.text


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------

class TestOverlap:
    def test_consecutive_chunks_overlap(self):
        doc = make_doc("word " * 200)
        splitter = small_splitter(chunk_size=50, chunk_overlap=10)
        chunks = splitter.split(doc)
        assert len(chunks) >= 2
        # The second chunk starts before the first chunk ends
        assert chunks[1].start_char < chunks[0].end_char

    def test_overlap_text_is_shared(self):
        """The tail of chunk[n] should appear at the head of chunk[n+1]."""
        doc = make_doc("word " * 200)
        splitter = small_splitter(chunk_size=50, chunk_overlap=10)
        chunks = splitter.split(doc)
        assert len(chunks) >= 2
        # The overlap region from chunk[0] must be present somewhere in chunk[1]
        overlap_text = doc.text[chunks[1].start_char: chunks[0].end_char]
        assert overlap_text in chunks[1].text

    def test_zero_overlap_chunks_do_not_overlap(self):
        doc = make_doc("word " * 200)
        splitter = small_splitter(chunk_size=50, chunk_overlap=0)
        chunks = splitter.split(doc)
        assert len(chunks) >= 2
        # With zero overlap, start of next chunk >= end of previous
        for i in range(1, len(chunks)):
            assert chunks[i].start_char >= chunks[i - 1].end_char


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    def _chunks(self) -> list:
        doc = make_doc("word " * 200, doc_id="sample.txt")
        return small_splitter().split(doc)

    def test_metadata_has_source(self):
        for chunk in self._chunks():
            assert "source" in chunk.metadata

    def test_metadata_has_chunk_index(self):
        chunks = self._chunks()
        for i, chunk in enumerate(chunks):
            assert chunk.metadata["chunk_index"] == i

    def test_metadata_has_chunk_count(self):
        chunks = self._chunks()
        total = len(chunks)
        for chunk in chunks:
            assert chunk.metadata["chunk_count"] == total

    def test_metadata_has_strategy(self):
        for chunk in self._chunks():
            assert chunk.metadata["strategy"] == "recursive"

    def test_metadata_has_chunk_size(self):
        splitter = small_splitter(chunk_size=50)
        doc = make_doc("word " * 200)
        for chunk in splitter.split(doc):
            assert chunk.metadata["chunk_size"] == 50

    def test_metadata_has_chunk_overlap(self):
        splitter = small_splitter(chunk_overlap=10)
        doc = make_doc("word " * 200)
        for chunk in splitter.split(doc):
            assert chunk.metadata["chunk_overlap"] == 10

    def test_document_metadata_propagated(self):
        doc = Document(
            id="book.pdf",
            source="/raw/book.pdf",
            text="word " * 200,
            metadata={"type": "pdf", "pages": 42, "source": "book.pdf"},
        )
        chunks = small_splitter().split(doc)
        for chunk in chunks:
            assert chunk.metadata["type"] == "pdf"
            assert chunk.metadata["pages"] == 42


# ---------------------------------------------------------------------------
# split_many
# ---------------------------------------------------------------------------

class TestSplitMany:
    def test_split_many_aggregates_chunks(self):
        docs = [make_doc("word " * 100, doc_id=f"doc{i}.txt") for i in range(3)]
        splitter = small_splitter()
        all_chunks = splitter.split_many(docs)
        doc_ids = {c.document_id for c in all_chunks}
        assert doc_ids == {"doc0.txt", "doc1.txt", "doc2.txt"}

    def test_split_many_empty_list(self):
        assert DocumentSplitter().split_many([]) == []
