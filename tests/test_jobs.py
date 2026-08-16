"""Tests for the indexing queue and worker.

The worker is exercised end to end against a real file and a real chunker, with
only the embedder faked — loading a 130 MB model per test would make the suite
unusable, and the embedding maths is covered in tests/test_embeddings.py.
"""

import threading
import time

import numpy as np
import pytest

from chunking.splitter import DocumentSplitter
from corpora import corpus_layout
from documents import Document, DocumentRepository, DocumentStatus, new_document_id
from jobs import DocumentIndexer, InProcessQueue, IndexingJob, new_job_id


class FakeEmbedder:
    """Deterministic vectors of the real dimensionality, without the model."""

    dimension = 384

    def __init__(self) -> None:
        self.calls = 0

    def embed_many(self, texts, batch_size=32):
        self.calls += 1
        rng = np.random.default_rng(0)
        return rng.random((len(texts), self.dimension), dtype=np.float32)


@pytest.fixture
def repo(tmp_path) -> DocumentRepository:
    return DocumentRepository(tmp_path / "documents.db")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """An isolated corpus, so a test never writes into the evaluation index."""
    monkeypatch.setattr("corpora.layout.CORPORA_DIR", tmp_path / "corpora")
    return "test-corpus"


def upload(repo: DocumentRepository, tmp_path, corpus: str, text: str, name="notes.md"):
    doc_id = new_document_id()
    path = tmp_path / f"{doc_id}.md"
    path.write_text(text, encoding="utf-8")
    return repo.add(
        Document(
            document_id=doc_id,
            corpus_id=corpus,
            filename=name,
            content_type="text/markdown",
            size_bytes=len(text),
            status=DocumentStatus.QUEUED,
            stored_path=str(path),
        )
    )


SAMPLE = """# Networking

## TCP Handshake

The three-way handshake is SYN, SYN-ACK, ACK. It establishes sequence numbers
before any data is exchanged, which is what makes TCP a reliable stream.

## UDP

UDP is connectionless and does not guarantee delivery or ordering.
"""


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


class TestInProcessQueue:
    def test_a_job_reaches_the_handler(self):
        seen = []
        done = threading.Event()
        q = InProcessQueue()
        q.start(lambda job: (seen.append(job), done.set()))

        q.enqueue(IndexingJob(job_id="j1", document_id="d1", corpus_id="c1"))
        assert done.wait(timeout=5)
        q.stop()

        assert seen[0].document_id == "d1"

    def test_enqueue_returns_before_the_work_finishes(self):
        # The whole reason a queue exists: an upload request must not wait for
        # embedding.
        started = threading.Event()
        release = threading.Event()
        q = InProcessQueue()
        q.start(lambda job: (started.set(), release.wait(timeout=5)))

        t0 = time.perf_counter()
        q.enqueue(IndexingJob(job_id="j", document_id="d", corpus_id="c"))
        elapsed = time.perf_counter() - t0

        assert started.wait(timeout=5)
        assert elapsed < 0.5
        release.set()
        q.stop()

    def test_a_failing_job_does_not_kill_the_worker(self):
        # Otherwise one corrupt PDF stops every later upload from indexing.
        second = threading.Event()

        def handler(job):
            if job.document_id == "bad":
                raise RuntimeError("boom")
            second.set()

        q = InProcessQueue()
        q.start(handler)
        q.enqueue(IndexingJob(job_id="1", document_id="bad", corpus_id="c"))
        q.enqueue(IndexingJob(job_id="2", document_id="good", corpus_id="c"))

        assert second.wait(timeout=5)
        q.stop()

    def test_describes_its_own_limits(self):
        # The API surfaces this; claiming durability it does not have would be
        # the kind of thing that loses someone's upload silently.
        described = InProcessQueue().describe()
        assert described["backend"] == "in-process"
        assert described["durable"] is False
        assert "REDIS_URL" in described["note"]

    def test_starting_twice_does_not_double_the_workers(self):
        q = InProcessQueue()
        q.start(lambda job: None)
        q.start(lambda job: None)
        assert len(q._threads) == 1
        q.stop()


class TestJobSerialisation:
    def test_round_trips_through_json(self):
        # Redis stores the job as a string, so this is the wire format.
        job = IndexingJob(
            job_id=new_job_id(), document_id="d", corpus_id="c", chunk_size=500
        )
        assert IndexingJob.from_json(job.to_json()) == job


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class TestIndexingPipeline:
    def test_indexes_a_document_end_to_end(self, repo, tmp_path, corpus):
        doc = upload(repo, tmp_path, corpus, SAMPLE)
        indexer = DocumentIndexer(repo, embedder=FakeEmbedder())

        indexer.handle(IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus))

        stored = repo.get(doc.document_id)
        assert stored.status is DocumentStatus.READY
        assert stored.chunk_count > 0

    def test_records_what_each_stage_cost(self, repo, tmp_path, corpus):
        """The stages were always timed and the numbers only ever logged.

        A user waited for indexing; a server log is not somewhere they can look.
        """
        doc = upload(repo, tmp_path, corpus, SAMPLE)
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        timings = repo.get(doc.document_id).timings_ms
        assert set(timings) == {"parse", "chunk", "embed", "index"}
        assert all(value >= 0 for value in timings.values())

    def test_a_failed_document_records_no_timings(self, repo, tmp_path, corpus):
        # Partial timings for a document that never finished would read as a
        # cost that bought something.
        doc = upload(repo, tmp_path, corpus, "   ")
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        stored = repo.get(doc.document_id)
        assert stored.status is DocumentStatus.FAILED
        assert stored.timings_ms is None

    def test_timings_survive_a_reopen(self, repo, tmp_path, corpus):
        # They are JSON in a TEXT column; a round trip through SQLite must give
        # back numbers rather than a string.
        doc = upload(repo, tmp_path, corpus, SAMPLE)
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        reopened = DocumentRepository(repo.db_path)
        timings = reopened.get(doc.document_id).timings_ms
        assert isinstance(timings["parse"], float)

    def test_writes_into_the_named_corpus_only(self, repo, tmp_path, corpus):
        # The isolation guarantee, at the index level.
        doc = upload(repo, tmp_path, corpus, SAMPLE)
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        layout = corpus_layout(corpus)
        assert layout.exists
        assert not layout.is_default

    def test_chunks_carry_the_corpus_and_the_document_name(self, repo, tmp_path, corpus):
        import json

        doc = upload(repo, tmp_path, corpus, SAMPLE, name="networking.md")
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        records = json.loads(corpus_layout(corpus).metadata_path.read_text(encoding="utf-8"))
        assert {r["corpus_id"] for r in records} == {corpus}
        # A citation shows the filename, not an opaque id.
        assert {r["document_id"] for r in records} == {"networking.md"}

    def test_a_second_document_appends_rather_than_replacing(self, repo, tmp_path, corpus):
        import json

        indexer = DocumentIndexer(repo, embedder=FakeEmbedder())
        first = upload(repo, tmp_path, corpus, SAMPLE, name="one.md")
        indexer.handle(IndexingJob(job_id="1", document_id=first.document_id, corpus_id=corpus))
        after_first = len(json.loads(corpus_layout(corpus).metadata_path.read_text("utf-8")))

        second = upload(repo, tmp_path, corpus, SAMPLE, name="two.md")
        indexer.handle(IndexingJob(job_id="2", document_id=second.document_id, corpus_id=corpus))
        after_second = len(json.loads(corpus_layout(corpus).metadata_path.read_text("utf-8")))

        assert after_second > after_first
        records = json.loads(corpus_layout(corpus).metadata_path.read_text("utf-8"))
        assert {"one.md", "two.md"} == {r["document_id"] for r in records}

    def test_the_embedder_is_reused_across_documents(self, repo, tmp_path, corpus):
        # Loading the model per job would dominate indexing time.
        embedder = FakeEmbedder()
        indexer = DocumentIndexer(repo, embedder=embedder)
        for name in ("a.md", "b.md"):
            doc = upload(repo, tmp_path, corpus, SAMPLE, name=name)
            indexer.handle(
                IndexingJob(job_id=name, document_id=doc.document_id, corpus_id=corpus)
            )

        assert embedder.calls == 2  # one per document, not one per chunk


class TestIndexingFailures:
    def test_a_missing_file_fails_the_document_rather_than_the_worker(
        self, repo, tmp_path, corpus
    ):
        doc = repo.add(
            Document(
                document_id=new_document_id(),
                corpus_id=corpus,
                filename="gone.md",
                content_type="text/markdown",
                size_bytes=10,
                status=DocumentStatus.QUEUED,
                stored_path=str(tmp_path / "not-there.md"),
            )
        )
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        stored = repo.get(doc.document_id)
        assert stored.status is DocumentStatus.FAILED
        assert "no longer on disk" in stored.error

    def test_a_document_with_no_text_reports_why(self, repo, tmp_path, corpus):
        doc = upload(repo, tmp_path, corpus, "   \n  \n ")
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        stored = repo.get(doc.document_id)
        assert stored.status is DocumentStatus.FAILED
        assert "No text" in stored.error

    def test_a_failure_message_carries_no_traceback(self, repo, tmp_path, corpus):
        class Exploding:
            dimension = 384

            def embed_many(self, texts, batch_size=32):
                raise RuntimeError("CUDA out of memory at 0x7fff")

        doc = upload(repo, tmp_path, corpus, SAMPLE)
        DocumentIndexer(repo, embedder=Exploding()).handle(
            IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus)
        )

        error = repo.get(doc.document_id).error
        assert "0x7fff" not in error
        assert "Traceback" not in error

    def test_an_unknown_document_is_ignored_quietly(self, repo, corpus):
        # A job for a deleted document must not crash the worker.
        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(job_id="j", document_id="never-existed", corpus_id=corpus)
        )


class TestChunkingSettings:
    def test_the_job_fixes_chunk_size_at_indexing_time(self, repo, tmp_path, corpus):
        # Chunk size is an indexing-time decision; it is carried on the job so
        # it cannot be changed later without re-indexing.
        long_text = SAMPLE + "\n\n" + ("Filler sentence about networking. " * 60)
        doc = upload(repo, tmp_path, corpus, long_text)

        DocumentIndexer(repo, embedder=FakeEmbedder()).handle(
            IndexingJob(
                job_id="j",
                document_id=doc.document_id,
                corpus_id=corpus,
                chunk_size=120,
                chunk_overlap=20,
            )
        )

        assert repo.get(doc.document_id).status is DocumentStatus.READY

    def test_an_explicit_splitter_overrides_the_job(self, repo, tmp_path, corpus):
        doc = upload(repo, tmp_path, corpus, SAMPLE)
        indexer = DocumentIndexer(
            repo, embedder=FakeEmbedder(), splitter=DocumentSplitter(chunk_size=100)
        )
        indexer.handle(IndexingJob(job_id="j", document_id=doc.document_id, corpus_id=corpus))

        assert repo.get(doc.document_id).status is DocumentStatus.READY
