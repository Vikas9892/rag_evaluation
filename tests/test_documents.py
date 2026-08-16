"""Tests for document records, lifecycle and upload safety.

The storage tests are mostly about refusing input. A filename arrives from a
browser, is attacker-controlled, and is the input to a filesystem write.
"""

import pytest
from typing import Iterator

from documents import (
    MAX_UPLOAD_BYTES,
    Document,
    DocumentRepository,
    DocumentStatus,
    EmptyFile,
    FileTooLarge,
    UnsupportedFileType,
    new_document_id,
    progress_fraction,
    read_limited,
    remove_stored_file,
    safe_display_name,
    store,
    suffix_of,
    validate,
)
from documents.models import STAGE_ORDER


@pytest.fixture
def repo(tmp_path) -> Iterator[DocumentRepository]:
    with DocumentRepository(tmp_path / "documents.db") as repository:
        yield repository


def make_doc(**overrides) -> Document:
    base = dict(
        document_id=new_document_id(),
        corpus_id="workspace",
        filename="handbook.pdf",
        content_type="application/pdf",
        size_bytes=2048,
    )
    base.update(overrides)
    return Document(**base)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_a_new_document_starts_uploading(self):
        assert make_doc().status is DocumentStatus.UPLOADING

    def test_progress_increases_through_the_pipeline(self):
        values = [progress_fraction(s) for s in STAGE_ORDER]
        assert values == sorted(values)
        assert values[-1] == 1.0

    def test_a_failure_reports_no_progress(self):
        # A bar stuck at 60% reads as "still working", which is the opposite of
        # what happened.
        assert progress_fraction(DocumentStatus.FAILED) == 0.0

    def test_the_stages_are_the_workers_real_stages(self):
        # Not a progress bar invented for the UI.
        assert [s.value for s in STAGE_ORDER] == [
            "UPLOADING",
            "QUEUED",
            "PARSING",
            "CHUNKING",
            "EMBEDDING",
            "INDEXING",
            "READY",
        ]

    def test_the_stored_path_never_reaches_a_client(self):
        # It is a server filesystem path.
        doc = make_doc(stored_path="/srv/uploads/workspace/abc.pdf")
        assert "stored_path" not in doc.as_dict()

    def test_the_serialised_form_carries_progress(self):
        assert make_doc().as_dict()["progress"] == pytest.approx(1 / len(STAGE_ORDER))


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestRepository:
    def test_round_trips_a_document(self, repo):
        doc = repo.add(make_doc())
        loaded = repo.get(doc.document_id)

        assert loaded is not None
        assert loaded.filename == "handbook.pdf"
        assert loaded.status is DocumentStatus.UPLOADING

    def test_returns_none_for_an_unknown_id(self, repo):
        assert repo.get("nope") is None

    def test_advances_status(self, repo):
        doc = repo.add(make_doc())
        repo.set_status(doc.document_id, DocumentStatus.EMBEDDING)

        assert repo.get(doc.document_id).status is DocumentStatus.EMBEDDING

    def test_records_a_failure_reason(self, repo):
        doc = repo.add(make_doc())
        repo.set_status(doc.document_id, DocumentStatus.FAILED, error="corrupt PDF")

        loaded = repo.get(doc.document_id)
        assert loaded.status is DocumentStatus.FAILED
        assert loaded.error == "corrupt PDF"

    def test_a_later_success_clears_the_old_failure_reason(self, repo):
        # Otherwise a retried document keeps showing why it failed last time.
        doc = repo.add(make_doc())
        repo.set_status(doc.document_id, DocumentStatus.FAILED, error="corrupt PDF")
        repo.set_status(doc.document_id, DocumentStatus.READY, chunk_count=12)

        loaded = repo.get(doc.document_id)
        assert loaded.error is None
        assert loaded.chunk_count == 12

    def test_lists_newest_first(self, repo):
        first = repo.add(make_doc(filename="one.pdf"))
        second = repo.add(make_doc(filename="two.pdf"))

        assert [d.document_id for d in repo.list()][:2] == [
            second.document_id,
            first.document_id,
        ]

    def test_lists_only_the_requested_corpus(self, repo):
        # The isolation guarantee, at the record level.
        repo.add(make_doc(corpus_id="alpha", filename="a.pdf"))
        repo.add(make_doc(corpus_id="beta", filename="b.pdf"))

        assert [d.filename for d in repo.list("alpha")] == ["a.pdf"]

    def test_deletes(self, repo):
        doc = repo.add(make_doc())
        assert repo.delete(doc.document_id) is True
        assert repo.get(doc.document_id) is None

    def test_deleting_an_unknown_document_reports_it(self, repo):
        assert repo.delete("nope") is False


class TestDuplicateDetection:
    def test_finds_an_identical_file_in_the_same_corpus(self, repo):
        repo.add(make_doc(content_sha256="abc123"))
        assert repo.find_by_hash("workspace", "abc123") is not None

    def test_the_same_file_in_another_corpus_is_not_a_duplicate(self, repo):
        # Two collections legitimately hold the same document.
        repo.add(make_doc(corpus_id="alpha", content_sha256="abc123"))
        assert repo.find_by_hash("beta", "abc123") is None

    def test_a_failed_upload_does_not_block_a_retry(self, repo):
        doc = repo.add(make_doc(content_sha256="abc123"))
        repo.set_status(doc.document_id, DocumentStatus.FAILED, error="corrupt")

        assert repo.find_by_hash("workspace", "abc123") is None


# ---------------------------------------------------------------------------
# Upload safety
# ---------------------------------------------------------------------------


class TestFilenameSafety:
    @pytest.mark.parametrize(
        "hostile,expected_suffix",
        [
            ("../../etc/passwd.txt", ".txt"),
            ("..\\..\\windows\\system32\\notes.md", ".md"),
            ("/absolute/path/report.pdf", ".pdf"),
            ("C:\\Users\\me\\report.pdf", ".pdf"),
        ],
    )
    def test_only_the_final_component_survives(self, hostile, expected_suffix):
        safe = safe_display_name(hostile)
        assert "/" not in safe and "\\" not in safe
        assert ".." not in safe
        assert suffix_of(hostile) == expected_suffix

    def test_strips_control_characters_and_null_bytes(self):
        assert safe_display_name("re\x00port\n.pdf") == "report.pdf"

    def test_never_returns_an_empty_name(self):
        # A name that sanitises to nothing must still be storable.
        assert safe_display_name("../../..") == "upload"
        assert safe_display_name("") == "upload"

    def test_caps_the_length(self):
        assert len(safe_display_name("a" * 500 + ".pdf")) <= 120

    def test_the_stored_file_is_named_by_id_not_by_the_upload(
        self, tmp_path, monkeypatch
    ):
        # Even a name that survives sanitising cannot collide with another.
        monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path)
        path, _ = store("workspace", "docid123", "report.pdf", b"data")

        assert path.name == "docid123.pdf"
        assert path.parent == tmp_path / "workspace"

    def test_storing_returns_the_content_hash(self, tmp_path, monkeypatch):
        monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path)
        _, digest = store("workspace", "docid123", "a.txt", b"hello")

        assert digest == (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )


class TestValidation:
    @pytest.mark.parametrize("name", ["a.pdf", "a.txt", "a.md", "a.markdown", "A.PDF"])
    def test_accepts_the_formats_a_parser_exists_for(self, name):
        validate(name, 1024)

    @pytest.mark.parametrize(
        "name", ["a.docx", "a.exe", "a.zip", "noextension", "a.pdf.exe"]
    )
    def test_refuses_anything_with_no_parser(self, name):
        # Accepting a format nothing can parse produces a document that never
        # leaves PARSING.
        with pytest.raises(UnsupportedFileType):
            validate(name, 1024)

    def test_refuses_an_empty_file(self):
        with pytest.raises(EmptyFile):
            validate("a.pdf", 0)

    def test_refuses_an_oversized_file(self):
        with pytest.raises(FileTooLarge):
            validate("a.pdf", MAX_UPLOAD_BYTES + 1)

    def test_accepts_a_file_exactly_at_the_limit(self):
        validate("a.pdf", MAX_UPLOAD_BYTES)

    def test_the_error_says_what_was_expected(self):
        with pytest.raises(UnsupportedFileType) as exc:
            validate("a.docx", 10)
        assert ".pdf" in str(exc.value)


class TestReadLimited:
    def test_reads_one_byte_past_the_limit_so_oversize_is_detectable(self):
        import io

        data = io.BytesIO(b"x" * 100)
        assert len(read_limited(data, limit=10)) == 11

    def test_returns_everything_when_under_the_limit(self):
        import io

        assert read_limited(io.BytesIO(b"short"), limit=100) == b"short"


class TestRemoveStoredFile:
    """Deleting the bytes, not only the record.

    DELETE unlinked a recorded path inside a try/except that logged and moved
    on, then reported "Document, file and chunks removed" either way. On
    Windows an indexing job still holding the file makes that unlink fail, so
    the reply claimed a deletion that had not happened and the upload stayed on
    disk indefinitely.
    """

    def test_removes_the_upload_by_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path)
        directory = tmp_path / "corpus-a"
        directory.mkdir()
        (directory / "abc123.md").write_text("content", encoding="utf-8")

        assert remove_stored_file("corpus-a", "abc123") is True
        assert not (directory / "abc123.md").exists()

    def test_leaves_another_documents_file_alone(self, tmp_path, monkeypatch):
        monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path)
        directory = tmp_path / "corpus-a"
        directory.mkdir()
        (directory / "abc123.md").write_text("mine", encoding="utf-8")
        (directory / "def456.md").write_text("theirs", encoding="utf-8")

        remove_stored_file("corpus-a", "abc123")

        assert (directory / "def456.md").exists()

    def test_reports_false_when_there_was_nothing_to_remove(
        self, tmp_path, monkeypatch
    ):
        # The caller uses this to decide what to tell the user, so "nothing
        # happened" must be distinguishable from "done".
        monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path)
        assert remove_stored_file("never-existed", "abc123") is False

    def test_an_unremovable_file_is_reported_rather_than_raised(
        self, tmp_path, monkeypatch
    ):
        # Windows refuses to unlink a file another thread holds open. The
        # delete request has already done its real work by then.
        monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path)
        directory = tmp_path / "corpus-a"
        directory.mkdir()
        (directory / "abc123.md").write_text("locked", encoding="utf-8")

        def refuse(self):
            raise PermissionError("file is open in another process")

        monkeypatch.setattr("pathlib.Path.unlink", refuse)

        assert remove_stored_file("corpus-a", "abc123") is False
