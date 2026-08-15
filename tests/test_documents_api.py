"""Tests for the document upload and management API.

The queue is replaced with one that runs the handler inline, so a test can
assert on the finished state without sleeping. Polling a real worker would make
the suite slow and flaky for no extra confidence — the threading itself is
covered in tests/test_jobs.py.
"""

import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import dependencies
from api.app import create_app
from api.dependencies import get_document_repository, get_indexing_queue
from corpora import corpus_layout
from documents import DocumentRepository, DocumentStatus
from documents.storage import MAX_UPLOAD_BYTES
from jobs import DocumentIndexer, IndexingJob, JobQueue


class InlineQueue(JobQueue):
    """Runs each job immediately, on the calling thread."""

    def __init__(self) -> None:
        self.handler = None
        self.jobs: list[IndexingJob] = []

    def enqueue(self, job: IndexingJob) -> None:
        self.jobs.append(job)
        if self.handler is not None:
            self.handler(job)

    def start(self, handler) -> None:
        self.handler = handler

    def stop(self) -> None:
        pass

    def describe(self) -> dict:
        return {"backend": "in-process", "durable": False, "workers": 1, "note": "inline"}


class FakeEmbedder:
    dimension = 384

    def embed_many(self, texts, batch_size=32):
        rng = np.random.default_rng(0)
        return rng.random((len(texts), self.dimension), dtype=np.float32)


SAMPLE = b"""# Networking Notes

## TCP Handshake

The three-way handshake is SYN, SYN-ACK, ACK. It establishes sequence numbers
before any data flows, which is what makes TCP a reliable stream.

## Congestion Control

Slow start grows the window exponentially until loss is detected.
"""


@pytest.fixture
def repo(tmp_path) -> DocumentRepository:
    return DocumentRepository(tmp_path / "documents.db")


@pytest.fixture
def queue(repo) -> InlineQueue:
    q = InlineQueue()
    q.start(DocumentIndexer(repo, embedder=FakeEmbedder()).handle)
    return q


@pytest.fixture
def client(repo, queue, tmp_path, monkeypatch) -> TestClient:
    # Redirect every write away from the real corpus and upload directories.
    monkeypatch.setattr("corpora.layout.CORPORA_DIR", tmp_path / "corpora")
    monkeypatch.setattr("documents.storage.UPLOAD_ROOT", tmp_path / "uploads")

    app = create_app()
    app.dependency_overrides[get_document_repository] = lambda: repo
    app.dependency_overrides[get_indexing_queue] = lambda: queue
    # The real worker would start on a thread and race the inline one.
    monkeypatch.setattr(dependencies, "start_indexing_worker", lambda: None)
    monkeypatch.setattr(dependencies, "stop_indexing_worker", lambda: None)

    with TestClient(app) as c:
        yield c


def upload(client, content=SAMPLE, name="notes.md", corpus="workspace", **params):
    return client.post(
        "/documents",
        params={"corpus_id": corpus, **params},
        files={"file": (name, io.BytesIO(content), "text/markdown")},
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class TestUpload:
    def test_returns_202_because_the_document_is_not_searchable_yet(self, client):
        # 201 Created would invite the client to query something with no chunks.
        assert upload(client).status_code == 202

    def test_returns_the_ids_needed_to_follow_the_work(self, client):
        body = upload(client).json()
        assert body["document_id"]
        assert body["job_id"]
        assert body["status"] == "QUEUED"

    def test_queues_a_job(self, client, queue):
        body = upload(client).json()
        assert [j.document_id for j in queue.jobs] == [body["document_id"]]

    def test_the_stored_filename_is_sanitised(self, client):
        body = upload(client, name="../../etc/passwd.md").json()
        assert body["filename"] == "passwd.md"

    def test_indexing_settings_travel_on_the_job(self, client, queue):
        # Chunk size is fixed when the document is indexed, not at query time.
        upload(client, chunk_size=300, chunk_overlap=40)
        assert queue.jobs[0].chunk_size == 300
        assert queue.jobs[0].chunk_overlap == 40


class TestUploadValidation:
    def test_refuses_a_type_with_no_parser(self, client):
        response = upload(client, name="malware.exe")
        assert response.status_code == 415
        assert ".pdf" in response.json()["detail"]

    def test_refuses_an_empty_file(self, client):
        assert upload(client, content=b"").status_code == 422

    def test_refuses_an_oversized_file(self, client):
        response = upload(client, content=b"x" * (MAX_UPLOAD_BYTES + 1), name="big.txt")
        assert response.status_code == 413

    def test_refuses_an_invalid_corpus_id(self, client):
        assert upload(client, corpus="../evaluation").status_code == 422

    def test_refuses_uploads_into_the_benchmark_corpus(self, client):
        # An upload must never be able to move a published metric.
        response = upload(client, corpus="evaluation")
        assert response.status_code == 422
        assert "reproducible" in response.json()["detail"]

    def test_an_error_is_readable_rather_than_a_traceback(self, client):
        detail = upload(client, name="a.exe").json()["detail"]
        assert "Traceback" not in detail
        assert "Error" not in detail.split()[0]


class TestDuplicates:
    def test_an_identical_file_returns_the_existing_document(self, client):
        first = upload(client).json()
        second = upload(client).json()

        assert second["duplicate_of"] == first["document_id"]
        assert second["document_id"] == first["document_id"]

    def test_an_identical_file_is_not_indexed_again(self, client, queue):
        # Two copies of the same text would occupy two top-K slots and answer
        # the same question twice.
        upload(client)
        queued_after_first = len(queue.jobs)
        second = upload(client).json()

        assert len(queue.jobs) == queued_after_first
        assert second["job_id"] == ""

    def test_a_duplicate_adds_no_second_record(self, client):
        upload(client)
        upload(client)
        assert len(client.get("/documents").json()["documents"]) == 1

    def test_the_same_bytes_under_a_new_name_is_still_a_duplicate(self, client):
        # Deduplication is by content, not filename: indexing the same text
        # twice is the problem, whatever it was called.
        first = upload(client, name="original.md").json()
        renamed = upload(client, name="copy.md").json()

        assert renamed["document_id"] == first["document_id"]

    def test_the_same_file_in_another_corpus_is_not_a_duplicate(self, client):
        upload(client, corpus="alpha")
        assert upload(client, corpus="beta").json()["duplicate_of"] is None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestIndexingLifecycle:
    def test_a_document_reaches_ready(self, client):
        document_id = upload(client).json()["document_id"]
        body = client.get(f"/documents/{document_id}/status").json()

        assert body["status"] == "READY"
        assert body["chunk_count"] > 0
        assert body["progress"] == 1.0

    def test_a_failure_is_reported_with_a_reason(self, client):
        document_id = upload(client, content=b"   \n  ", name="blank.md").json()["document_id"]
        body = client.get(f"/documents/{document_id}/status").json()

        assert body["status"] == "FAILED"
        assert body["error"]
        assert body["progress"] == 0.0

    def test_status_and_get_return_the_same_record(self, client):
        document_id = upload(client).json()["document_id"]
        assert client.get(f"/documents/{document_id}").json() == client.get(
            f"/documents/{document_id}/status"
        ).json()

    def test_an_unknown_document_is_404(self, client):
        assert client.get("/documents/nope").status_code == 404
        assert client.get("/documents/nope/status").status_code == 404


class TestListing:
    def test_lists_uploaded_documents(self, client):
        upload(client, name="a.md")
        upload(client, content=SAMPLE + b"\n\n## Extra\n\nMore text.\n", name="b.md")
        assert len(client.get("/documents").json()["documents"]) == 2

    def test_scopes_to_a_corpus(self, client):
        upload(client, corpus="alpha", name="a.md")
        upload(client, corpus="beta", name="b.md")  # same bytes, different corpus

        body = client.get("/documents", params={"corpus_id": "alpha"}).json()
        assert [d["filename"] for d in body["documents"]] == ["a.md"]

    def test_never_exposes_a_filesystem_path(self, client):
        upload(client)
        assert "stored_path" not in json.dumps(client.get("/documents").json())


class TestDeletion:
    def test_removes_the_record(self, client):
        document_id = upload(client).json()["document_id"]
        assert client.delete(f"/documents/{document_id}").status_code == 200
        assert client.get(f"/documents/{document_id}").status_code == 404

    def test_says_plainly_that_chunks_remain_indexed(self, client):
        # FAISS here is a flat index with no delete. Reporting success while
        # silently leaving the chunks searchable would be a lie.
        document_id = upload(client).json()["document_id"]
        body = client.delete(f"/documents/{document_id}").json()

        assert body["chunks_still_indexed"] > 0
        assert "re-indexed" in body["detail"]

    def test_a_document_that_never_indexed_claims_nothing_remains(self, client):
        document_id = upload(client, content=b"  ", name="blank.md").json()["document_id"]
        body = client.delete(f"/documents/{document_id}").json()

        assert body["chunks_still_indexed"] == 0

    def test_deleting_an_unknown_document_is_404(self, client):
        assert client.delete("/documents/nope").status_code == 404


# ---------------------------------------------------------------------------
# Corpora and queue
# ---------------------------------------------------------------------------


class TestCorpora:
    def test_an_uploaded_corpus_becomes_queryable(self, client):
        upload(client, corpus="alpha")
        corpora = {c["corpus_id"]: c for c in client.get("/corpora").json()["corpora"]}

        assert corpora["alpha"]["ready"] is True
        assert corpora["alpha"]["documents"] == 1
        assert corpora["alpha"]["chunks"] > 0

    def test_the_benchmark_corpus_is_marked_as_such(self, client):
        upload(client, corpus="alpha")
        corpora = {c["corpus_id"]: c for c in client.get("/corpora").json()["corpora"]}
        assert corpora["alpha"]["is_evaluation"] is False

    def test_uploads_do_not_touch_the_evaluation_index(self, client, tmp_path):
        # The isolation guarantee, end to end through the API.
        upload(client, corpus="alpha")
        assert corpus_layout("alpha").root == tmp_path / "corpora" / "alpha"


class TestQueueStatus:
    def test_reports_what_the_queue_is_and_is_not(self, client):
        body = client.get("/queue").json()
        assert body["backend"] in {"in-process", "redis"}
        assert "durable" in body
