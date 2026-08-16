"""Persistence for document records.

SQLite, from the standard library. A JSON file would need its own locking to
survive a worker thread and a request handler writing at once, which is the
problem SQLite already solves; and no new dependency enters the project for it.

The database holds records *about* documents. Chunks, vectors and indexes stay
where they are, on disk under the corpus layout.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from config.logging_config import get_logger
from config.settings import INDEX_DIR
from documents.models import Document, DocumentStatus, _now

logger = get_logger(__name__)

DEFAULT_DB_PATH = INDEX_DIR / "documents.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    corpus_id       TEXT NOT NULL,
    filename        TEXT NOT NULL,
    content_type    TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    status          TEXT NOT NULL,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    stored_path     TEXT,
    content_sha256  TEXT,
    timings_ms      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_corpus_idx ON documents (corpus_id);
CREATE INDEX IF NOT EXISTS documents_sha_idx ON documents (corpus_id, content_sha256);
"""


#: Columns added after the table first shipped. CREATE TABLE IF NOT EXISTS
#: leaves an existing database alone, so a column added to _SCHEMA above is
#: absent from every database created before it and every query naming it
#: fails — on a developer's machine and on a deployment that has been running.
_ADDED_COLUMNS = {"timings_ms": "TEXT"}


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    present = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
    for column, declaration in _ADDED_COLUMNS.items():
        if column not in present:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {declaration}")


class DocumentRepository:
    """Stores and retrieves document records.

    One connection per thread: SQLite connections are not safe to share across
    threads, and the worker runs on a different one from the request handlers.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            _add_missing_columns(conn)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            # WAL lets the worker write while a request reads, instead of the
            # two blocking each other on every status poll.
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        with conn:
            yield conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(self, document: Document) -> Document:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, corpus_id, filename, content_type, size_bytes,
                    status, chunk_count, error, stored_path, content_sha256,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.document_id,
                    document.corpus_id,
                    document.filename,
                    document.content_type,
                    document.size_bytes,
                    document.status.value,
                    document.chunk_count,
                    document.error,
                    document.stored_path,
                    document.content_sha256,
                    document.created_at,
                    document.updated_at,
                ),
            )
        return document

    def set_status(
        self,
        document_id: str,
        status: DocumentStatus,
        *,
        error: Optional[str] = None,
        chunk_count: Optional[int] = None,
        timings_ms: Optional[dict] = None,
    ) -> None:
        """Advance a document's stage.

        `error` is cleared on any non-FAILED transition, so a document that
        failed, was retried and succeeded does not keep showing the old reason.
        """
        fields = ["status = ?", "updated_at = ?"]
        values: list = [status.value, _now()]

        if status is DocumentStatus.FAILED:
            fields.append("error = ?")
            values.append(error)
        else:
            fields.append("error = NULL")

        if chunk_count is not None:
            fields.append("chunk_count = ?")
            values.append(chunk_count)

        if timings_ms is not None:
            fields.append("timings_ms = ?")
            values.append(json.dumps(timings_ms))

        values.append(document_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE documents SET {', '.join(fields)} WHERE document_id = ?", values
            )

    def delete(self, document_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE document_id = ?", (document_id,)
            )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, document_id: str) -> Optional[Document]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE document_id = ?", (document_id,)
            ).fetchone()
        return _to_document(row) if row else None

    def list(self, corpus_id: Optional[str] = None) -> List[Document]:
        """Newest first, optionally scoped to one corpus."""
        query = "SELECT * FROM documents"
        params: tuple = ()
        if corpus_id is not None:
            query += " WHERE corpus_id = ?"
            params = (corpus_id,)
        query += " ORDER BY created_at DESC, rowid DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_to_document(r) for r in rows]

    def find_by_hash(self, corpus_id: str, content_sha256: str) -> Optional[Document]:
        """An identical file already in this corpus, if there is one.

        Scoped to the corpus because the same file uploaded to two collections
        is two documents, not a duplicate.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM documents
                WHERE corpus_id = ? AND content_sha256 = ? AND status != ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (corpus_id, content_sha256, DocumentStatus.FAILED.value),
            ).fetchone()
        return _to_document(row) if row else None

    def unfinished(self) -> List[Document]:
        """Documents left mid-pipeline, oldest first.

        A document in PARSING or EMBEDDING when the process died is stuck: the
        queue held the job in memory and nothing will pick it up again. These
        are what startup requeues.
        """
        terminal = (DocumentStatus.READY.value, DocumentStatus.FAILED.value)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE status NOT IN (?, ?) ORDER BY created_at",
                terminal,
            ).fetchall()
        return [_to_document(r) for r in rows]

    def corpus_ids(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT corpus_id FROM documents ORDER BY corpus_id"
            ).fetchall()
        return [r["corpus_id"] for r in rows]


def _to_document(row: sqlite3.Row) -> Document:
    return Document(
        document_id=row["document_id"],
        corpus_id=row["corpus_id"],
        filename=row["filename"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        status=DocumentStatus(row["status"]),
        chunk_count=row["chunk_count"],
        error=row["error"],
        stored_path=row["stored_path"],
        content_sha256=row["content_sha256"],
        timings_ms=json.loads(row["timings_ms"]) if row["timings_ms"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
