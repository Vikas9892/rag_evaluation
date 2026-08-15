"""Document records and their lifecycle."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DocumentStatus(str, Enum):
    """Where a document is in the indexing pipeline.

    These are the worker's actual stages, not a progress bar invented for the
    UI. A document reports EMBEDDING because the worker is embedding it; if a
    stage is ever removed, this enum has to change with it.
    """

    UPLOADING = "UPLOADING"
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"


#: Ordered so a UI can render progress without hardcoding the pipeline.
STAGE_ORDER = (
    DocumentStatus.UPLOADING,
    DocumentStatus.QUEUED,
    DocumentStatus.PARSING,
    DocumentStatus.CHUNKING,
    DocumentStatus.EMBEDDING,
    DocumentStatus.INDEXING,
    DocumentStatus.READY,
)

#: Statuses from which nothing further happens on its own.
TERMINAL = frozenset({DocumentStatus.READY, DocumentStatus.FAILED})


def progress_fraction(status: DocumentStatus) -> float:
    """How far through the pipeline a document is, in [0, 1].

    FAILED returns 0.0 rather than a partial value: a bar that stops at 60%
    reads as "still working", which is the opposite of what happened.
    """
    if status is DocumentStatus.FAILED:
        return 0.0
    return (STAGE_ORDER.index(status) + 1) / len(STAGE_ORDER)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Document:
    """One uploaded file and everything known about indexing it."""

    document_id: str
    corpus_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus = DocumentStatus.UPLOADING
    chunk_count: int = 0
    error: Optional[str] = None
    stored_path: Optional[str] = None
    #: Hash of the file's bytes, so the same upload twice is recognisable.
    content_sha256: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        data["progress"] = progress_fraction(self.status)
        # stored_path is a server filesystem path. It is useful internally and
        # is never part of what a client is handed.
        data.pop("stored_path", None)
        return data
