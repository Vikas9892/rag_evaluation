"""Document upload and management.

Upload returns 202 Accepted, not 201: the document exists as a record but is not
yet searchable, and telling a client it was created would invite it to query
something that has no chunks.

The router validates and hands off. Parsing, chunking, embedding and indexing
happen on the worker in `jobs/indexer.py`.
"""

import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from api.dependencies import (
    get_document_repository,
    get_indexing_queue,
    invalidate_service_cache,
)
from api.schemas import (
    CorpusListResponse,
    CorpusSummary,
    DocumentCreateResponse,
    DocumentListResponse,
    DocumentResponse,
    QueueStatusResponse,
)
from config.logging_config import get_logger
from corpora import (
    DEFAULT_CORPUS_ID,
    remove_document,
    InvalidCorpusIdError,
    corpus_layout,
    is_valid_corpus_id,
    list_corpus_ids,
)
from documents import (
    Document,
    DocumentRepository,
    DocumentStatus,
    EmptyFile,
    FileTooLarge,
    UnsupportedFileType,
    new_document_id,
    read_limited,
    remove_stored_file,
    safe_display_name,
    store,
    validate,
)
from documents.storage import MAX_UPLOAD_BYTES
from jobs import IndexingJob, JobQueue, new_job_id

logger = get_logger(__name__)
router = APIRouter(tags=["documents"])

#: Where uploads go unless the caller says otherwise. Deliberately not the
#: evaluation corpus: an upload must never change a published benchmark number.
DEFAULT_UPLOAD_CORPUS = "workspace"


def _require_valid_corpus(corpus_id: str) -> str:
    if not is_valid_corpus_id(corpus_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid corpus id: use lowercase letters, digits, '-' or '_', "
                "starting with a letter or digit."
            ),
        )
    return corpus_id


@router.post(
    "/documents",
    response_model=DocumentCreateResponse,
    status_code=202,
    summary="Upload a document for indexing",
    description=(
        "Accepts the file, records it and queues indexing. Returns 202 because the "
        "document is not searchable yet — poll `GET /documents/{id}/status` until it "
        "reports READY."
    ),
    responses={
        413: {"description": "File exceeds the size limit"},
        415: {"description": "No parser exists for this file type"},
        422: {"description": "Empty file or invalid corpus id"},
    },
)
async def upload_document(
    file: UploadFile = File(...),
    corpus_id: str = Query(default=DEFAULT_UPLOAD_CORPUS),
    chunk_size: Optional[int] = Query(default=None, ge=50, le=4000),
    chunk_overlap: Optional[int] = Query(default=None, ge=0, le=1000),
    repository: DocumentRepository = Depends(get_document_repository),
    queue: JobQueue = Depends(get_indexing_queue),
) -> DocumentCreateResponse:
    _require_valid_corpus(corpus_id)
    if corpus_id == DEFAULT_CORPUS_ID:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{DEFAULT_CORPUS_ID}' is the benchmark corpus and is built offline. "
                "Upload to a different corpus so published metrics stay reproducible."
            ),
        )

    filename = safe_display_name(file.filename or "upload")
    # One byte past the limit, so oversize is detectable without reading a file
    # of unbounded size into memory first.
    data = read_limited(file.file, MAX_UPLOAD_BYTES)

    try:
        validate(filename, len(data))
    except FileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except EmptyFile as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    document_id = new_document_id()
    digest = hashlib.sha256(data).hexdigest()

    # Indexing the same bytes twice puts two identical chunks in the corpus,
    # which then occupy two of the top-K slots and answer the same question
    # twice. The existing document is returned instead, so the caller learns
    # what happened without the index being polluted to tell them.
    existing = repository.find_by_hash(corpus_id, digest)
    if existing is not None:
        return DocumentCreateResponse(
            document_id=existing.document_id,
            job_id="",
            corpus_id=corpus_id,
            status=existing.status.value,
            filename=existing.filename,
            duplicate_of=existing.document_id,
        )

    try:
        path, _ = store(corpus_id, document_id, filename, data)
    except (OSError, InvalidCorpusIdError) as exc:
        logger.exception("Could not store upload %s", filename)
        # `from exc` keeps the cause on the traceback the server logs; the
        # client is told only that storing failed.
        raise HTTPException(
            status_code=500, detail="Could not store the uploaded file."
        ) from exc

    repository.add(
        Document(
            document_id=document_id,
            corpus_id=corpus_id,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(data),
            status=DocumentStatus.QUEUED,
            stored_path=str(path),
            content_sha256=digest,
        )
    )

    job = IndexingJob(
        job_id=new_job_id(),
        document_id=document_id,
        corpus_id=corpus_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    queue.enqueue(job)

    return DocumentCreateResponse(
        document_id=document_id,
        job_id=job.job_id,
        corpus_id=corpus_id,
        status=DocumentStatus.QUEUED.value,
        filename=filename,
        # Always None here: the duplicate case returned above. The conditional
        # this replaces read as though both outcomes were live.
        duplicate_of=None,
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List uploaded documents",
)
async def list_documents(
    corpus_id: Optional[str] = Query(default=None),
    repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentListResponse:
    if corpus_id is not None:
        _require_valid_corpus(corpus_id)
    return DocumentListResponse(
        corpus_id=corpus_id,
        documents=[DocumentResponse(**d.as_dict()) for d in repository.list(corpus_id)],
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="One document",
    responses={404: {"description": "No such document"}},
)
async def get_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentResponse:
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No such document.")
    return DocumentResponse(**document.as_dict())


@router.get(
    "/documents/{document_id}/status",
    response_model=DocumentResponse,
    summary="Indexing status",
    description=(
        "The same record as `GET /documents/{id}`, exposed separately because it is "
        "the endpoint a client polls while indexing runs."
    ),
    responses={404: {"description": "No such document"}},
)
async def document_status(
    document_id: str,
    repository: DocumentRepository = Depends(get_document_repository),
) -> DocumentResponse:
    return await get_document(document_id, repository)


@router.delete(
    "/documents/{document_id}",
    status_code=200,
    summary="Delete a document",
    description=(
        "Removes the record, the stored file and the document's chunks. The corpus "
        "index is rebuilt from the vectors already on disk, so nothing is re-embedded."
    ),
    responses={404: {"description": "No such document"}},
)
async def delete_document(
    document_id: str,
    repository: DocumentRepository = Depends(get_document_repository),
) -> dict:
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="No such document.")

    # Whether the bytes are gone is tracked, not assumed: an indexing job that
    # still has the file open makes Windows refuse the unlink, and the reply
    # used to claim "file removed" regardless. When that happens the worker
    # clears it as it finishes, so the file goes either way — but not yet, and
    # a delete confirmation should not describe a state that has not arrived.
    file_removed = True
    if document.stored_path:
        file_removed = remove_stored_file(document.corpus_id, document_id)

    try:
        removal = remove_document(document.corpus_id, document_id)
    except ValueError as exc:
        # An inconsistent index is a real problem and must not be papered over
        # by deleting the record and leaving the chunks orphaned.
        logger.error("Refusing to remove %s: %s", document_id, exc)
        raise HTTPException(status_code=409, detail=str(exc))

    repository.delete(document_id)
    # The next query must not be answered by a retriever loaded before this.
    invalidate_service_cache(document.corpus_id)

    return {
        "document_id": document_id,
        "deleted": True,
        "chunks_removed": removal.removed_chunks,
        "chunks_remaining": removal.remaining_chunks,
        "corpus_deleted": removal.corpus_deleted,
        "file_removed": file_removed,
        "detail": _deletion_detail(removal, file_removed),
    }


def _deletion_detail(removal, file_removed: bool) -> str:
    subject = "Document, file and" if file_removed else "Document and"
    if removal.corpus_deleted:
        detail = (
            f"{subject} chunks removed; the corpus was empty afterwards and "
            "has been deleted."
        )
    else:
        detail = f"{subject} {removal.removed_chunks} chunk(s) removed."
    if not file_removed:
        detail += " The uploaded file is still being indexed and is removed "
        detail += "when that finishes."
    return detail


@router.get(
    "/corpora",
    response_model=CorpusListResponse,
    summary="Collections available to query",
)
async def list_corpora(
    repository: DocumentRepository = Depends(get_document_repository),
) -> CorpusListResponse:
    """Every corpus with an index, plus any that only exist as records so far."""
    summaries: list[CorpusSummary] = []
    seen: set[str] = set()

    for corpus_id in list_corpus_ids():
        docs = repository.list(corpus_id)
        summaries.append(
            CorpusSummary(
                corpus_id=corpus_id,
                documents=len(docs),
                chunks=sum(d.chunk_count for d in docs),
                ready=True,
                is_evaluation=corpus_id == DEFAULT_CORPUS_ID,
            )
        )
        seen.add(corpus_id)

    # A corpus whose first upload is still indexing has records but no index. It
    # is listed as not ready rather than hidden, so the UI can show it working.
    for corpus_id in repository.corpus_ids():
        if corpus_id in seen:
            continue
        docs = repository.list(corpus_id)
        summaries.append(
            CorpusSummary(
                corpus_id=corpus_id,
                documents=len(docs),
                chunks=sum(d.chunk_count for d in docs),
                ready=corpus_layout(corpus_id).exists,
                is_evaluation=False,
            )
        )

    return CorpusListResponse(corpora=summaries)


@router.get(
    "/queue",
    response_model=QueueStatusResponse,
    summary="What the indexing queue is",
    description=(
        "Reported rather than assumed: the default queue is in-process and loses "
        "jobs on restart, which a client showing an indexing spinner should know."
    ),
)
async def queue_status(
    queue: JobQueue = Depends(get_indexing_queue),
) -> QueueStatusResponse:
    return QueueStatusResponse(**queue.describe())
