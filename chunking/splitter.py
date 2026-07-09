from typing import List, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.logging_config import get_logger
from config.settings import CHUNK_OVERLAP, CHUNK_SIZE, SEPARATORS
from ingestion.document import Document

from .chunk import Chunk

logger = get_logger(__name__)


class DocumentSplitter:
    """Splits a Document into a list of Chunk objects using recursive character splitting.

    The splitter tries separators in order (\n\n → \n → ". " → " " → "") so
    chunks align to paragraph/sentence/word boundaries before falling back to
    raw character slicing.  Overlap ensures context is preserved across chunk
    boundaries.
    """

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        separators: List[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators if separators is not None else SEPARATORS
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=self.separators,
            length_function=len,
            is_separator_regex=False,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(self, document: Document) -> List[Chunk]:
        """Split one Document into Chunk objects."""
        if not document.text.strip():
            logger.debug("Document '%s' is empty — returning no chunks", document.id)
            return []

        raw_chunks: List[str] = self._splitter.split_text(document.text)
        total = len(raw_chunks)
        chunks: List[Chunk] = []
        search_pos = 0

        for idx, chunk_text in enumerate(raw_chunks):
            start, end = self._locate(document.text, chunk_text, search_pos)
            metadata = {
                **document.metadata,
                "chunk_index": idx,
                "chunk_count": total,
                "strategy": "recursive",
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
            }
            chunks.append(
                Chunk(
                    chunk_id=f"{document.id}_chunk_{idx:04d}",
                    document_id=document.id,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                    metadata=metadata,
                )
            )
            # Advance the search cursor past this chunk, minus the overlap window.
            search_pos = max(search_pos, start + len(chunk_text) - self.chunk_overlap)

        logger.info("'%s' -> %d chunk(s)", document.id, total)
        return chunks

    def split_many(self, documents: List[Document]) -> List[Chunk]:
        """Split a list of Documents, returning a flat list of Chunks."""
        all_chunks: List[Chunk] = []
        for doc in documents:
            all_chunks.extend(self.split(doc))
        return all_chunks

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _locate(self, text: str, chunk: str, hint: int) -> Tuple[int, int]:
        """Return (start, end) char offsets for chunk inside text.

        Searches forward from hint to stay monotonic across chunks.
        Falls back to a full scan if the hint overshoots (shouldn't happen
        under normal use but keeps the code robust).
        """
        start = text.find(chunk, hint)
        if start == -1:
            start = text.find(chunk)
        if start == -1:
            start = hint
        return start, start + len(chunk)
