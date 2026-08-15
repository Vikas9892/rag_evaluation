"""Chunking configuration.

Grouped into one object because these three values only make sense together —
a minimum larger than half the chunk size collapses a document into one blob,
and an overlap approaching the chunk size duplicates most of the corpus.

**Chunking is an indexing-time decision.** Changing any of it requires
re-embedding and rebuilding the index, so it cannot be a query parameter. The
API says so explicitly rather than leaving a UI free to offer it as a slider
beside top-K, which would imply an instant effect it cannot have.
"""

from dataclasses import dataclass
from typing import List, Optional

from config.settings import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_CHARS, SEPARATORS


class InvalidChunkingConfig(ValueError):
    """A combination that would produce a useless index."""


@dataclass(frozen=True)
class ChunkingConfig:
    """How a document is split, fixed at the moment it is indexed."""

    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP
    min_chunk_chars: int = MIN_CHUNK_CHARS
    separators: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.chunk_size < 50:
            raise InvalidChunkingConfig(
                "chunk_size must be at least 50 characters; below that a chunk cannot "
                "hold a complete sentence."
            )
        if self.chunk_overlap < 0:
            raise InvalidChunkingConfig("chunk_overlap cannot be negative.")
        if self.chunk_overlap >= self.chunk_size:
            # The splitter would make no forward progress, or duplicate nearly
            # the whole document across neighbouring chunks.
            raise InvalidChunkingConfig(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than chunk_size "
                f"({self.chunk_size})."
            )
        if self.min_chunk_chars < 0:
            raise InvalidChunkingConfig("min_chunk_chars cannot be negative.")

    @property
    def effective_min_chunk_chars(self) -> int:
        """The minimum the splitter will actually apply.

        Clamped below half the chunk size: a threshold at or above chunk_size
        classifies every chunk as short and cascades the document into one blob.
        The clamp lives here as well as in the splitter so a caller can see what
        its setting will really do.
        """
        return max(0, min(self.min_chunk_chars, self.chunk_size // 2))

    def as_dict(self) -> dict:
        return {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "min_chunk_chars": self.effective_min_chunk_chars,
        }


#: What the offline pipeline and the workspace both use unless told otherwise.
DEFAULT_CHUNKING = ChunkingConfig(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    min_chunk_chars=MIN_CHUNK_CHARS,
    separators=SEPARATORS,
)
