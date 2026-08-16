import os
from functools import lru_cache
from typing import Callable

from fastapi import HTTPException

from config.logging_config import get_logger
from generation.generator import GroqGenerator
from generation.prompt_builder import PromptBuilder
from corpora import DEFAULT_CORPUS_ID, CorpusNotFoundError, is_valid_corpus_id
from retrieval.hybrid_retriever import HybridRetriever
from documents import DocumentRepository, DocumentStatus
from jobs import (
    DocumentIndexer,
    IndexingJob,
    InProcessQueue,
    JobQueue,
    RedisQueue,
    new_job_id,
)
from services.rag_service import RAGService

logger = get_logger(__name__)


@lru_cache(maxsize=8)
def _build_service_for(corpus_id: str) -> RAGService:
    """One service per corpus, built once and kept.

    Cached because loading an index and its BM25 store costs real time, and a
    query should not pay it. The bound is small on purpose: each entry holds a
    corpus in memory, so an unbounded cache would grow with every corpus ever
    queried.

    The generator and prompt builder are per-service but stateless; the
    expensive part is the retriever.
    """
    logger.info("Loading RAG pipeline for corpus %r...", corpus_id)
    retriever = HybridRetriever.from_corpus(corpus_id)
    service = RAGService(
        retriever=retriever, generator=GroqGenerator(), builder=PromptBuilder()
    )
    logger.info("RAG pipeline ready for corpus %r", corpus_id)
    return service


def _build_service() -> RAGService:
    """The evaluation corpus, which is what every existing caller means."""
    return _build_service_for(DEFAULT_CORPUS_ID)


def get_service_for_corpus(corpus_id: str) -> RAGService:
    """Resolve a corpus to its service, translating failures into HTTP.

    A corpus that was never indexed is a 404: the caller asked for something
    that does not exist. An invalid id is a 422: the caller asked for something
    that could not exist.
    """
    if not is_valid_corpus_id(corpus_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid corpus id: use lowercase letters, digits, '-' or '_', "
                "starting with a letter or digit."
            ),
        )
    try:
        return _build_service_for(corpus_id)
    except CorpusNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Corpus {corpus_id!r} has no index yet. Upload a document and wait "
                "for it to report READY."
            ),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Index not available: {exc}")
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


def get_service_resolver() -> Callable[[str], RAGService]:
    """Injected so the corpus can be chosen from the request body.

    A plain `Depends(get_service)` cannot see the body, and calling the resolver
    directly from the router would bypass dependency overrides and make the
    endpoints untestable. Injecting the *function* keeps both.
    """
    return get_service_for_corpus


def invalidate_service_cache(corpus_id: str | None = None) -> None:
    """Drop cached services so a newly indexed document becomes searchable.

    Called after indexing. Without it a corpus queried before its first upload
    finished would keep serving the retriever it loaded then, and the new
    document would appear to have vanished.
    """
    _build_service_for.cache_clear()


@lru_cache(maxsize=1)
def _build_document_repository() -> DocumentRepository:
    return DocumentRepository()


def get_document_repository() -> DocumentRepository:
    """One repository per process; SQLite handles the per-thread connections."""
    return _build_document_repository()


@lru_cache(maxsize=1)
def _build_indexing_queue() -> JobQueue:
    """Redis when it is configured, otherwise a worker thread.

    Chosen here rather than in the router so the whole application shares one
    queue — two queues would mean jobs enqueued by a request that no worker
    consumes.
    """
    url = os.environ.get("REDIS_URL")
    if url:
        try:
            queue: JobQueue = RedisQueue(url)
            logger.info("Indexing queue: Redis at %s", url)
            return queue
        except Exception:
            # A misconfigured Redis must not stop the API from serving. Falling
            # back is loud, not silent.
            logger.exception(
                "REDIS_URL is set but unusable — falling back to in-process"
            )

    logger.info("Indexing queue: in-process worker thread")
    return InProcessQueue()


def get_indexing_queue() -> JobQueue:
    return _build_indexing_queue()


def start_indexing_worker() -> None:
    """Begin draining the queue, and recover anything a restart stranded.

    The in-process queue holds jobs in memory, so a restart loses whatever had
    not finished — a document would sit at EMBEDDING forever with nothing coming
    to move it. The *records* are durable even when the queue is not, so startup
    requeues every document that is neither READY nor FAILED.

    Re-running a half-finished job is safe by construction: indexing writes the
    document's chunks and rebuilds the index from scratch, so the second run
    produces the same result as the first. With Redis this is unnecessary, and
    harmless.
    """
    repository = get_document_repository()
    queue = get_indexing_queue()
    indexer = DocumentIndexer(repository, on_indexed=invalidate_service_cache)
    queue.start(indexer.handle)

    stranded = repository.unfinished()
    for document in stranded:
        # Reset the stage too, so a status poll stops claiming a stage that
        # nothing is working on.
        repository.set_status(document.document_id, DocumentStatus.QUEUED)
        queue.enqueue(
            IndexingJob(
                job_id=new_job_id(),
                document_id=document.document_id,
                corpus_id=document.corpus_id,
            )
        )
    if stranded:
        logger.info(
            "Requeued %d document(s) left unfinished by a restart", len(stranded)
        )


def stop_indexing_worker() -> None:
    # Order matters: the worker writes document status, so it has to be stopped
    # before the connections it writes through are closed.
    get_indexing_queue().stop()

    # cache_clear before close, so anything that asks for a repository after
    # shutdown builds a fresh one rather than being handed a closed one. This
    # is what a TestClient does between two `with` blocks in the same process.
    repository = _build_document_repository()
    _build_document_repository.cache_clear()
    repository.close()


def get_service() -> RAGService:
    """FastAPI dependency that returns the process-scoped RAGService singleton."""
    try:
        return _build_service()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Index not available: {exc}")
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
