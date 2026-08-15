"""Tests for the durability story: Redis, and recovery without it.

The Redis tests run against a stub client rather than a server. That covers
*this* code — the key it pushes to, the blocking pop, the serialisation, the
shutdown — and does not pretend to test Redis itself. Requiring a live server
would make the suite unrunnable on a laptop for no extra confidence in the part
that can actually be wrong here.
"""

import sys
import threading
import types

import pytest

from documents import Document, DocumentRepository, DocumentStatus, new_document_id
from jobs import IndexingJob, RedisQueue


class StubRedis:
    """The three operations RedisQueue uses, over an in-memory list."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.from_url_calls: list[str] = []

    def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    def blpop(self, key: str, timeout: int = 0):
        items = self.lists.get(key, [])
        if not items:
            return None
        return (key, items.pop(0))


@pytest.fixture
def stub_redis(monkeypatch) -> StubRedis:
    """Install a fake `redis` module for the duration of one test."""
    client = StubRedis()
    module = types.ModuleType("redis")
    module.Redis = types.SimpleNamespace(
        from_url=lambda url, decode_responses=True: client  # noqa: ARG005
    )
    monkeypatch.setitem(sys.modules, "redis", module)
    return client


class TestRedisQueue:
    def test_enqueue_pushes_the_serialised_job(self, stub_redis):
        queue = RedisQueue("redis://localhost:6379")
        job = IndexingJob(job_id="j1", document_id="d1", corpus_id="c1")

        queue.enqueue(job)

        raw = stub_redis.lists["rag:indexing:jobs"][0]
        assert IndexingJob.from_json(raw) == job

    def test_a_pushed_job_reaches_the_handler(self, stub_redis):
        seen: list[IndexingJob] = []
        done = threading.Event()
        queue = RedisQueue("redis://localhost:6379")
        queue.enqueue(IndexingJob(job_id="j1", document_id="d1", corpus_id="c1"))

        queue.start(lambda job: (seen.append(job), done.set()))
        assert done.wait(timeout=5)
        queue.stop()

        assert seen[0].document_id == "d1"

    def test_a_failing_job_does_not_stop_the_consumer(self, stub_redis):
        second = threading.Event()

        def handler(job: IndexingJob) -> None:
            if job.document_id == "bad":
                raise RuntimeError("boom")
            second.set()

        queue = RedisQueue("redis://localhost:6379")
        queue.enqueue(IndexingJob(job_id="1", document_id="bad", corpus_id="c"))
        queue.enqueue(IndexingJob(job_id="2", document_id="good", corpus_id="c"))
        queue.start(handler)

        assert second.wait(timeout=5)
        queue.stop()

    def test_uses_a_namespaced_key(self, stub_redis):
        # A bare key would collide with anything else on a shared Redis.
        RedisQueue("redis://localhost:6379").enqueue(
            IndexingJob(job_id="j", document_id="d", corpus_id="c")
        )
        assert "rag:indexing:jobs" in stub_redis.lists

    def test_reports_itself_as_durable(self, stub_redis):
        described = RedisQueue("redis://localhost:6379").describe()
        assert described["backend"] == "redis"
        assert described["durable"] is True

    def test_stopping_is_safe_before_starting(self, stub_redis):
        RedisQueue("redis://localhost:6379").stop()


class TestQueueSelection:
    def test_an_unusable_redis_url_falls_back_rather_than_failing_startup(
        self, monkeypatch
    ):
        # A misconfigured Redis must not stop the API from serving. The fallback
        # is logged, not silent.
        from api import dependencies

        broken = types.ModuleType("redis")

        def explode(*args, **kwargs):
            raise ConnectionError("no route to host")

        broken.Redis = types.SimpleNamespace(from_url=explode)
        monkeypatch.setitem(sys.modules, "redis", broken)
        monkeypatch.setenv("REDIS_URL", "redis://unreachable:6379")
        dependencies._build_indexing_queue.cache_clear()

        try:
            queue = dependencies._build_indexing_queue()
            assert queue.describe()["backend"] == "in-process"
        finally:
            dependencies._build_indexing_queue.cache_clear()

    def test_no_redis_url_means_in_process(self, monkeypatch):
        from api import dependencies

        monkeypatch.delenv("REDIS_URL", raising=False)
        dependencies._build_indexing_queue.cache_clear()
        try:
            assert dependencies._build_indexing_queue().describe()["backend"] == "in-process"
        finally:
            dependencies._build_indexing_queue.cache_clear()


class TestRestartRecovery:
    """The in-process queue is not durable, so startup repairs what it lost."""

    @pytest.fixture
    def repo(self, tmp_path) -> DocumentRepository:
        return DocumentRepository(tmp_path / "documents.db")

    def stranded(self, repo: DocumentRepository, status: DocumentStatus) -> Document:
        return repo.add(
            Document(
                document_id=new_document_id(),
                corpus_id="workspace",
                filename="notes.md",
                content_type="text/markdown",
                size_bytes=10,
                status=status,
            )
        )

    @pytest.mark.parametrize(
        "status",
        [
            DocumentStatus.QUEUED,
            DocumentStatus.PARSING,
            DocumentStatus.CHUNKING,
            DocumentStatus.EMBEDDING,
            DocumentStatus.INDEXING,
        ],
    )
    def test_every_mid_pipeline_stage_is_recoverable(self, repo, status):
        # A document left at EMBEDDING has nothing coming to move it: the job
        # was in memory and the memory is gone.
        self.stranded(repo, status)
        assert len(repo.unfinished()) == 1

    def test_finished_documents_are_not_requeued(self, repo):
        self.stranded(repo, DocumentStatus.READY)
        self.stranded(repo, DocumentStatus.FAILED)
        assert repo.unfinished() == []

    def test_recovery_requeues_and_resets_the_status(self, repo, monkeypatch):
        from api import dependencies

        document = self.stranded(repo, DocumentStatus.EMBEDDING)

        enqueued: list[IndexingJob] = []

        class CapturingQueue:
            def start(self, handler):
                pass

            def enqueue(self, job):
                enqueued.append(job)

        monkeypatch.setattr(dependencies, "get_document_repository", lambda: repo)
        monkeypatch.setattr(dependencies, "get_indexing_queue", lambda: CapturingQueue())

        dependencies.start_indexing_worker()

        assert [j.document_id for j in enqueued] == [document.document_id]
        # Reset, so a status poll does not keep claiming a stage nothing is on.
        assert repo.get(document.document_id).status is DocumentStatus.QUEUED

    def test_recovery_preserves_the_corpus(self, repo, monkeypatch):
        from api import dependencies

        repo.add(
            Document(
                document_id=new_document_id(),
                corpus_id="my-corpus",
                filename="a.md",
                content_type="text/markdown",
                size_bytes=10,
                status=DocumentStatus.PARSING,
            )
        )
        enqueued: list[IndexingJob] = []

        class CapturingQueue:
            def start(self, handler):
                pass

            def enqueue(self, job):
                enqueued.append(job)

        monkeypatch.setattr(dependencies, "get_document_repository", lambda: repo)
        monkeypatch.setattr(dependencies, "get_indexing_queue", lambda: CapturingQueue())

        dependencies.start_indexing_worker()

        assert enqueued[0].corpus_id == "my-corpus"
