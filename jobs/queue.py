"""Indexing job queue.

Indexing embeds every chunk of a document, which takes seconds to minutes. Doing
that inside the upload request would hold a connection open for the duration and
time out behind any proxy, so it happens on a worker instead.

Two implementations behind one interface:

* `InProcessQueue` — a worker thread in the API process. The default, because it
  needs no infrastructure and the work genuinely happens off the request.
* `RedisQueue` — used when REDIS_URL is set, so jobs survive a restart and more
  than one process can consume them.

The in-process queue is honest about its limits rather than pretending to be
durable: jobs are lost if the process dies, and two API processes would each run
their own worker. Both are stated in `describe()` and surfaced by the API.
"""

import json
import queue
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class IndexingJob:
    """One document's trip through the pipeline."""

    job_id: str
    document_id: str
    corpus_id: str
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "IndexingJob":
        return cls(**json.loads(raw))


def new_job_id() -> str:
    return uuid.uuid4().hex


#: What a queue hands a consumer.
JobHandler = Callable[[IndexingJob], None]


class JobQueue(ABC):
    """Somewhere to put work that must not happen during a request."""

    @abstractmethod
    def enqueue(self, job: IndexingJob) -> None: ...

    @abstractmethod
    def start(self, handler: JobHandler) -> None:
        """Begin consuming. Must return promptly; work happens elsewhere."""

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def describe(self) -> Dict[str, object]:
        """What this queue is and what it does not guarantee."""


class InProcessQueue(JobQueue):
    """A worker thread and an in-memory queue.

    Real asynchrony — the upload request returns before indexing starts — with
    no infrastructure. What it is not is durable: a job enqueued and not yet
    finished is lost if the process exits, and each API process runs its own
    worker over its own queue.
    """

    def __init__(self, workers: int = 1) -> None:
        self._queue: "queue.Queue[Optional[IndexingJob]]" = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._worker_count = workers
        self._running = False

    def enqueue(self, job: IndexingJob) -> None:
        self._queue.put(job)
        logger.info("Queued indexing job %s for document %s", job.job_id, job.document_id)

    def start(self, handler: JobHandler) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._worker_count):
            thread = threading.Thread(
                target=self._consume, args=(handler,), name=f"indexer-{i}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        logger.info("In-process indexing worker started (%d thread(s))", self._worker_count)

    def _consume(self, handler: JobHandler) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:  # shutdown sentinel
                    return
                handler(job)
            except Exception:
                # A failing job must not take the worker down with it, or one
                # corrupt PDF stops every later upload from being indexed.
                logger.exception("Indexing job %s failed", job.job_id)
            finally:
                self._queue.task_done()

    def stop(self) -> None:
        if not self._running:
            return
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads.clear()
        self._running = False

    def join(self, timeout: Optional[float] = None) -> None:
        """Block until the queue drains. For tests, not for request handling."""
        self._queue.join()

    def describe(self) -> Dict[str, object]:
        return {
            "backend": "in-process",
            "durable": False,
            "workers": self._worker_count,
            "note": (
                "Jobs run on a worker thread in the API process. They are lost if the "
                "process restarts, and each process consumes its own queue. Set "
                "REDIS_URL for a durable, shared queue."
            ),
        }


class RedisQueue(JobQueue):
    """A Redis list consumed by a worker thread.

    Jobs survive a restart and several processes can share the queue. Redis is
    imported inside the constructor so the package is only needed by deployments
    that actually use it.
    """

    def __init__(self, url: str, key: str = "rag:indexing:jobs") -> None:
        import redis  # imported here so the dependency stays optional

        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._key = key
        self._url = url
        self._thread: Optional[threading.Thread] = None
        self._stopping = threading.Event()

    def enqueue(self, job: IndexingJob) -> None:
        self._client.rpush(self._key, job.to_json())
        logger.info("Queued indexing job %s in Redis", job.job_id)

    def start(self, handler: JobHandler) -> None:
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._consume, args=(handler,), name="indexer-redis", daemon=True
        )
        self._thread.start()
        logger.info("Redis indexing worker started against %s", self._url)

    def _consume(self, handler: JobHandler) -> None:
        while not self._stopping.is_set():
            # Blocking pop with a timeout, so shutdown is noticed promptly
            # instead of after the next job arrives.
            item = self._client.blpop(self._key, timeout=1)
            if item is None:
                continue
            try:
                handler(IndexingJob.from_json(item[1]))
            except Exception:
                logger.exception("Indexing job failed")

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def describe(self) -> Dict[str, object]:
        return {
            "backend": "redis",
            "durable": True,
            "workers": 1,
            "note": "Jobs are stored in Redis and survive an API restart.",
        }
