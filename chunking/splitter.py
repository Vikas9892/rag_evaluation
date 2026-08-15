from typing import List, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.logging_config import get_logger
from config.settings import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_CHARS, SEPARATORS
from ingestion.document import Document

from .chunk import Chunk

logger = get_logger(__name__)

# (text, start_char, end_char) for one candidate chunk, before merging.
_Piece = Tuple[str, int, int]


class DocumentSplitter:
    """Splits a Document into a list of Chunk objects using recursive character splitting.

    The splitter tries separators in order (\n##  → \n###  → \n\n → \n → ". "
    → " " → "") so chunks align to heading, then paragraph/sentence/word
    boundaries before falling back to raw character slicing.  Splitting on
    headings first keeps one chunk to one concept, which sharpens retrieval:
    a chunk covering five sections matches every query about any of them.
    Overlap ensures context is preserved across chunk boundaries.
    """

    @classmethod
    def from_config(cls, config: "ChunkingConfig") -> "DocumentSplitter":
        """Build from a validated configuration.

        The individual keyword arguments stay for existing callers; this is the
        entry point for anything that carries chunking settings around as a
        unit, which is everything indexing-time.
        """
        return cls(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=config.separators,
            min_chunk_chars=config.min_chunk_chars,
        )

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
        separators: List[str] | None = None,
        min_chunk_chars: int = MIN_CHUNK_CHARS,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators if separators is not None else SEPARATORS
        # Clamped below half the chunk size: a threshold at or above chunk_size
        # would classify every chunk as short and cascade the whole document
        # into a single blob.
        self.min_chunk_chars = max(0, min(min_chunk_chars, chunk_size // 2))
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

        pieces: List[_Piece] = []
        search_pos = 0
        for chunk_text in raw_chunks:
            start, end = self._locate(document.text, chunk_text, search_pos)
            pieces.append((chunk_text, start, end))
            # Advance the search cursor past this chunk, minus the overlap window.
            search_pos = max(search_pos, start + len(chunk_text) - self.chunk_overlap)

        pieces = self._merge_short(pieces, document.text)

        total = len(pieces)
        chunks: List[Chunk] = []

        for idx, (chunk_text, start, end) in enumerate(pieces):
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

        if total != len(raw_chunks):
            logger.info(
                "'%s' -> %d chunk(s) (%d merged as shorter than %d chars)",
                document.id, total, len(raw_chunks) - total, self.min_chunk_chars,
            )
        else:
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

    def _merge_short(self, pieces: List[_Piece], source: str) -> List[_Piece]:
        """Fold chunks shorter than min_chunk_chars into their neighbour.

        Splitting on headings emits heading-only chunks such as
        "## ACID Properties".  Indexed alone they are pure noise: they match a
        query's phrasing closely while containing none of the answer, so they
        outrank the chunk that actually holds it.

        Short chunks merge *forward*, so a heading becomes the prefix of the
        section it introduces — the heading text is retained as signal rather
        than discarded.  A trailing short chunk has nothing to merge into, so it
        merges backward instead.  Content is never dropped: a document that is
        entirely shorter than the threshold survives as a single chunk.

        Merged text is re-sliced from the source so start/end offsets stay exact
        and the original separator between the parts is preserved.
        """
        if self.min_chunk_chars <= 0 or len(pieces) <= 1:
            return pieces

        merged: List[_Piece] = []
        pending: _Piece | None = None

        for text, start, end in pieces:
            if pending is not None:
                p_start, p_end = pending[1], pending[2]
                start, end = p_start, max(p_end, end)
                text = source[start:end]
                pending = None

            if len(text.strip()) < self.min_chunk_chars:
                pending = (text, start, end)  # carry into the next piece
                continue

            merged.append((text, start, end))

        if pending is not None:
            if merged:
                l_text, l_start, l_end = merged[-1]
                end = max(l_end, pending[2])
                merged[-1] = (source[l_start:end], l_start, end)
            else:
                merged.append(pending)  # whole document is below the threshold

        return merged

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
