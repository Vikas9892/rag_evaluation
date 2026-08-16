"""The indexing worker: parse → clean → chunk → embed → index.

Every step here already existed and is reused unchanged. This module is the
orchestration and the status reporting around them, not a second pipeline —
which is what keeps an uploaded corpus and the evaluation corpus retrievable by
the same code.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from chunking.chunk import Chunk
from chunking.config import DEFAULT_CHUNKING, ChunkingConfig, InvalidChunkingConfig
from chunking.splitter import DocumentSplitter
from config.logging_config import get_logger
from corpora import corpus_layout
from documents import DocumentRepository, DocumentStatus
from embeddings.embedder import Embedder, shared_embedder
from embeddings.storage import VectorStorage
from ingestion.cleaner import TextCleaner
from ingestion.document import Document as ParsedDocument
from ingestion.parser import MarkdownParser, PDFParser, TXTParser
from jobs.queue import IndexingJob
from retrieval.faiss_store import FAISSStore

logger = get_logger(__name__)

_PARSERS = {
    ".pdf": PDFParser,
    ".txt": TXTParser,
    ".md": MarkdownParser,
    ".markdown": MarkdownParser,
}


class IndexingError(RuntimeError):
    """A stage failed. The message is written to the document record."""


@dataclass
class StageTiming:
    """How long one stage took, for the performance figures the platform reports."""

    stage: str
    ms: float


class DocumentIndexer:
    """Runs one document through the pipeline and reports its progress.

    The embedder is injected and shared. Loading the model costs seconds and
    hundreds of megabytes, so constructing one per job would dominate indexing
    time and eventually exhaust memory.
    """

    def __init__(
        self,
        repository: DocumentRepository,
        embedder: Optional[Embedder] = None,
        splitter: Optional[DocumentSplitter] = None,
        cleaner: Optional[TextCleaner] = None,
        on_indexed: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._repo = repository
        self._embedder = embedder
        self._splitter = splitter
        self._cleaner = cleaner or TextCleaner()
        # Called with the corpus id after a successful index, so whoever caches
        # loaded retrievers can drop the stale one. Injected rather than
        # imported, to keep the worker independent of the API layer.
        self._on_indexed = on_indexed

    # ------------------------------------------------------------------

    def handle(self, job: IndexingJob) -> None:
        """Entry point for the queue. Never raises: failures land on the record."""
        document = self._repo.get(job.document_id)
        if document is None:
            logger.warning(
                "Job %s references unknown document %s", job.job_id, job.document_id
            )
            return

        timings: List[StageTiming] = []
        try:
            text = self._parse(job, Path(document.stored_path or ""), timings)
            chunks = self._chunk(job, text, document.filename, timings)
            vectors = self._embed(job, chunks, timings)
            self._index(job, vectors, chunks, timings)
        except IndexingError as exc:
            logger.warning("Indexing failed for %s: %s", job.document_id, exc)
            self._repo.set_status(
                job.document_id, DocumentStatus.FAILED, error=str(exc)
            )
            return
        except Exception as exc:  # noqa: BLE001 - the record must record something
            # The message reaches a user, so it says what failed rather than
            # carrying a traceback.
            logger.exception("Unexpected indexing failure for %s", job.document_id)
            self._repo.set_status(
                job.document_id,
                DocumentStatus.FAILED,
                error=f"Indexing failed while processing this document ({type(exc).__name__}).",
            )
            return

        self._repo.set_status(
            job.document_id,
            DocumentStatus.READY,
            chunk_count=len(chunks),
            # Recorded on the document rather than only in the log. The cost of
            # indexing is the thing a user waited for, and a server log is not
            # somewhere they can look.
            timings_ms={t.stage: round(t.ms, 1) for t in timings},
        )
        if self._on_indexed is not None:
            self._on_indexed(job.corpus_id)
        logger.info(
            "Indexed %s into corpus %s: %d chunks (%s)",
            document.filename,
            job.corpus_id,
            len(chunks),
            ", ".join(f"{t.stage} {t.ms:.0f}ms" for t in timings),
        )

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def _parse(self, job: IndexingJob, path: Path, timings: List[StageTiming]) -> str:
        self._repo.set_status(job.document_id, DocumentStatus.PARSING)
        t0 = time.perf_counter()

        if not path.is_file():
            raise IndexingError("The uploaded file is no longer on disk.")

        parser_cls = _PARSERS.get(path.suffix.lower())
        if parser_cls is None:
            raise IndexingError(f"No parser for {path.suffix} files.")

        try:
            raw, _ = parser_cls().parse(path)
        except Exception as exc:  # noqa: BLE001
            # A corrupt PDF is the common case and is the user's problem to fix,
            # so it is reported as a parse failure rather than a server error.
            raise IndexingError(
                f"Could not read this file — it may be corrupt or password protected "
                f"({type(exc).__name__})."
            ) from exc

        text = self._cleaner.clean(raw)
        if not text.strip():
            raise IndexingError("No text could be extracted — a scanned PDF needs OCR.")

        timings.append(StageTiming("parse", (time.perf_counter() - t0) * 1000))
        return text

    def _chunk(
        self, job: IndexingJob, text: str, filename: str, timings: List[StageTiming]
    ) -> List[Chunk]:
        self._repo.set_status(job.document_id, DocumentStatus.CHUNKING)
        t0 = time.perf_counter()

        try:
            splitter = self._splitter or self._build_splitter(job)
        except InvalidChunkingConfig as exc:
            raise IndexingError(str(exc)) from exc
        parsed = ParsedDocument(
            id=job.document_id,
            source=filename,
            text=text,
            metadata={"filename": filename},
        )
        chunks = splitter.split(parsed)

        if not chunks:
            raise IndexingError(
                "The document produced no chunks — it may be too short."
            )

        # The chunk's document_id is what a citation shows, so it carries the
        # filename rather than an opaque id; corpus_id is what scopes retrieval.
        for chunk in chunks:
            chunk.document_id = filename
            chunk.corpus_id = job.corpus_id
            chunk.metadata = {**(chunk.metadata or {}), "document_id": job.document_id}

        timings.append(StageTiming("chunk", (time.perf_counter() - t0) * 1000))
        return chunks

    def _embed(
        self, job: IndexingJob, chunks: List[Chunk], timings: List[StageTiming]
    ) -> np.ndarray:
        self._repo.set_status(job.document_id, DocumentStatus.EMBEDDING)
        t0 = time.perf_counter()

        embedder = self._embedder or shared_embedder()
        vectors = embedder.embed_many([c.text for c in chunks])

        timings.append(StageTiming("embed", (time.perf_counter() - t0) * 1000))
        return vectors

    def _index(
        self,
        job: IndexingJob,
        vectors: np.ndarray,
        chunks: List[Chunk],
        timings: List[StageTiming],
    ) -> None:
        self._repo.set_status(job.document_id, DocumentStatus.INDEXING)
        t0 = time.perf_counter()

        layout = corpus_layout(job.corpus_id)
        layout.root.mkdir(parents=True, exist_ok=True)
        storage = VectorStorage(layout.vectors_path, layout.metadata_path)

        # Append rather than rebuild. VectorStorage.append already existed and
        # is what makes a second upload cost one document's work instead of the
        # whole corpus's.
        if layout.vectors_path.exists() and layout.metadata_path.exists():
            storage.append(vectors, chunks)
        else:
            storage.save(vectors, chunks)

        all_vectors, _ = storage.load()
        store = FAISSStore(dimension=all_vectors.shape[1])
        store.add(all_vectors)
        store.save(layout.faiss_path)

        timings.append(StageTiming("index", (time.perf_counter() - t0) * 1000))

    @staticmethod
    def _build_splitter(job: IndexingJob) -> DocumentSplitter:
        """Chunking is an indexing-time decision, fixed when the job was created.

        Whatever the job carries is validated here rather than trusted: an
        overlap larger than the chunk size would otherwise produce an index
        nobody notices is broken until retrieval quality drops.
        """
        config = ChunkingConfig(
            chunk_size=job.chunk_size or DEFAULT_CHUNKING.chunk_size,
            chunk_overlap=(
                job.chunk_overlap
                if job.chunk_overlap is not None
                else DEFAULT_CHUNKING.chunk_overlap
            ),
            min_chunk_chars=DEFAULT_CHUNKING.min_chunk_chars,
            separators=DEFAULT_CHUNKING.separators,
        )
        return DocumentSplitter.from_config(config)
