from dataclasses import dataclass

from chunking.chunk import Chunk


@dataclass
class RetrievalResult:
    """A single ranked result returned by the Retriever.

    score  — cosine similarity in [-1, 1]; higher is more relevant
    rank   — 1-indexed position in the result list (1 = best match)
    chunk  — the source Chunk, ready for display or answer generation
    """

    chunk: Chunk
    score: float
    rank: int
