from typing import List

from config.logging_config import get_logger
from config.settings import TOP_K
from chunking.chunk import Chunk

from .ranking import RetrievalResult

logger = get_logger(__name__)


class BM25Store:
    """Sparse keyword retriever backed by BM25Okapi (rank-bm25).

    BM25 captures exact-term overlap that dense embeddings often miss — it is
    the sparse half of hybrid retrieval.  Tokenisation is naive (lower-case
    split on whitespace) which is sufficient for English-language technical
    documents but should be swapped for a language-aware tokeniser in production.
    """

    def __init__(self, chunks: List[Chunk]) -> None:
        from rank_bm25 import BM25Okapi

        self._chunks = chunks
        self._index = BM25Okapi(
            [c.text.lower().split() for c in chunks]
        ) if chunks else None
        logger.info("BM25Store ready: %d documents", len(chunks))

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = TOP_K) -> List[RetrievalResult]:
        """Return at most top_k chunks ranked by BM25 score (descending).

        Chunks with score 0.0 are excluded — they have no term overlap with
        the query and would dilute downstream fusion.
        """
        if self._index is None or not self._chunks:
            return []

        tokens = query.lower().split()
        scores = self._index.get_scores(tokens)

        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        results: List[RetrievalResult] = []
        for rank, (idx, score) in enumerate(indexed[:top_k], start=1):
            if score < 1e-10:
                break
            results.append(
                RetrievalResult(chunk=self._chunks[idx], score=float(score), rank=rank)
            )

        logger.debug(
            "BM25 query '%.40s...' -> %d result(s)", query, len(results)
        )
        return results

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def ntotal(self) -> int:
        return len(self._chunks)
