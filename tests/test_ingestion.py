"""Unit tests for Phase 1 — document ingestion pipeline."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.document import Document
from ingestion.cleaner import TextCleaner
from ingestion.parser import TXTParser, MarkdownParser
from ingestion.loader import DocumentLoader


# ---------------------------------------------------------------------------
# Document dataclass
# ---------------------------------------------------------------------------

class TestDocument:
    def test_fields_are_set(self):
        doc = Document(id="a.txt", source="/raw/a.txt", text="hello", metadata={"type": "txt"})
        assert doc.id == "a.txt"
        assert doc.text == "hello"
        assert doc.metadata["type"] == "txt"

    def test_equality(self):
        d1 = Document(id="x", source="x", text="hi", metadata={})
        d2 = Document(id="x", source="x", text="hi", metadata={})
        assert d1 == d2


# ---------------------------------------------------------------------------
# TextCleaner
# ---------------------------------------------------------------------------

class TestTextCleaner:
    def setup_method(self):
        self.cleaner = TextCleaner()

    def test_strips_null_bytes(self):
        assert "\x00" not in self.cleaner.clean("hello\x00world")

    def test_collapses_whitespace(self):
        result = self.cleaner.clean("a   b\t\tc")
        assert "  " not in result

    def test_strips_leading_trailing_whitespace(self):
        result = self.cleaner.clean("  hello  ")
        assert result == "hello"

    def test_preserves_paragraph_breaks(self):
        result = self.cleaner.clean("para1\n\npara2")
        assert "\n\n" in result

    def test_collapses_excessive_newlines(self):
        result = self.cleaner.clean("a\n\n\n\n\nb")
        assert "\n\n\n" not in result


# ---------------------------------------------------------------------------
# TXTParser
# ---------------------------------------------------------------------------

class TestTXTParser:
    def test_parse_valid_txt(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("Hello world", encoding="utf-8")
        parser = TXTParser()
        text, meta = parser.parse(f)
        assert text == "Hello world"
        assert meta["type"] == "txt"

    def test_metadata_contains_size(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("data", encoding="utf-8")
        _, meta = TXTParser().parse(f)
        assert "size" in meta


# ---------------------------------------------------------------------------
# MarkdownParser
# ---------------------------------------------------------------------------

class TestMarkdownParser:
    def test_parse_markdown(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nContent here.", encoding="utf-8")
        text, meta = MarkdownParser().parse(f)
        assert "Title" in text
        assert meta["type"] == "markdown"


# ---------------------------------------------------------------------------
# DocumentLoader
# ---------------------------------------------------------------------------

class TestDocumentLoader:
    def test_loads_txt_file(self, tmp_path):
        (tmp_path / "notes.txt").write_text("Some notes", encoding="utf-8")
        docs = DocumentLoader(tmp_path).load()
        assert len(docs) == 1
        assert docs[0].id == "notes.txt"

    def test_skips_unsupported_extension(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n")
        docs = DocumentLoader(tmp_path).load()
        assert len(docs) == 0

    def test_empty_file_returns_document_with_empty_text(self, tmp_path):
        (tmp_path / "empty.txt").write_text("", encoding="utf-8")
        docs = DocumentLoader(tmp_path).load()
        assert len(docs) == 1
        assert docs[0].text == ""

    def test_corrupted_file_is_skipped_gracefully(self, tmp_path):
        """A file that looks like PDF but is garbage should not crash the loader."""
        bad = tmp_path / "broken.pdf"
        bad.write_bytes(b"not a real pdf")
        (tmp_path / "good.txt").write_text("good content", encoding="utf-8")
        docs = DocumentLoader(tmp_path).load()
        # only the txt should be loaded
        assert len(docs) == 1
        assert docs[0].id == "good.txt"

    def test_metadata_contains_file_type(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Hi", encoding="utf-8")
        docs = DocumentLoader(tmp_path).load()
        assert docs[0].metadata["type"] == "markdown"

    def test_metadata_contains_source(self, tmp_path):
        (tmp_path / "readme.md").write_text("# Hi", encoding="utf-8")
        docs = DocumentLoader(tmp_path).load()
        assert "source" in docs[0].metadata

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            DocumentLoader(tmp_path / "nonexistent").load()

    def test_multiple_file_types(self, tmp_path):
        (tmp_path / "a.txt").write_text("txt content", encoding="utf-8")
        (tmp_path / "b.md").write_text("# md content", encoding="utf-8")
        docs = DocumentLoader(tmp_path).load()
        assert len(docs) == 2
        types = {d.metadata["type"] for d in docs}
        assert types == {"txt", "markdown"}
