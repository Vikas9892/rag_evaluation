from dataclasses import dataclass, field
from typing import Literal, Optional

from chunking.chunk import Chunk

#: Which retrieval strategy answered a request.
RetrieverMode = Literal["dense", "sparse", "hybrid"]


@dataclass(frozen=True)
class StageScore:
    """What one retrieval stage thought of one chunk.

    Both halves are needed. The score is the stage's own units — cosine
    similarity for dense, BM25 for sparse, an RRF sum for fusion — which are not
    comparable across stages, so the rank is what lets a reader see that dense
    put a chunk first and sparse put it ninth.
    """

    score: float
    rank: int


@dataclass
class RetrievalTrace:
    """Per-stage attribution for a single chunk.

    A stage is ``None`` when it did not rank this chunk. That covers two
    situations deliberately kept together here, because from the chunk's point
    of view they are the same absence:

    * the stage did not run at all (sparse, when ``retriever="dense"``), or
    * the stage ran and this chunk fell outside its candidate window.

    They are distinguished one level up: a response reports which retriever ran,
    so a client seeing ``retriever="hybrid"`` knows both stages executed and a
    ``None`` therefore means "this stage did not surface this chunk". This is
    the distinction the product spec insists the UI render differently — a stage
    that did not run is greyed out, a chunk one stage missed is not.

    ``None`` never means "scored zero". BM25 genuinely scores zero for a chunk
    with no term overlap, and that is a measurement; absence is not.
    """

    dense: Optional[StageScore] = None
    sparse: Optional[StageScore] = None
    fused: Optional[StageScore] = None
    reranker: Optional[StageScore] = None


@dataclass
class RetrievalResult:
    """A single ranked result returned by a retriever.

    score  — the final score, in the units of whichever stage ranked last
    rank   — 1-indexed position in the result list (1 = best match)
    chunk  — the source Chunk, ready for display or answer generation
    trace  — how each stage scored this chunk, for the retrieval table
    """

    chunk: Chunk
    score: float
    rank: int
    trace: RetrievalTrace = field(default_factory=RetrievalTrace)
