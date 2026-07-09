"""Cross-encoder re-ranking for second-stage retrieval quality improvement.

Architecture
------------
Stage 1 (fast):   Dense retrieval retrieves top-K*M candidates in ~5 ms
Stage 2 (slower): Cross-encoder scores each (query, passage) pair in isolation
                  and returns the true top-K

A cross-encoder reads query and passage jointly, so it captures fine-grained
relevance signals that bi-encoders (which encode independently) miss.  The
tradeoff is latency: ~50–200 ms per batch on CPU for MiniLM-L-6.

Default model: cross-encoder/ms-marco-MiniLM-L-6-v2
  — 22 M params, fast on CPU, strong on passage-retrieval benchmarks
"""
from abc import ABC, abstractmethod
from typing import List

from sentence_transformers import CrossEncoder

from config.logging_config import get_logger
from retrieval.ranking import RetrievalResult

logger = get_logger(__name__)


class BaseReranker(ABC):
    """Provider-agnostic interface for all re-rankers."""

    @abstractmethod
    def rerank(
        self, query: str, results: List[RetrievalResult], top_k: int
    ) -> List[RetrievalResult]:
        """Re-score and re-rank results; return the top_k highest-scoring ones."""


class CrossEncoderReranker(BaseReranker):
    """sentence-transformers CrossEncoder wrapped in the BaseReranker interface.

    Usage
    -----
    >>> reranker = CrossEncoderReranker()
    >>> reranked = reranker.rerank(query, initial_results, top_k=5)
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ) -> None:
        self._model = CrossEncoder(model_name)
        self._model_name = model_name
        logger.info("CrossEncoderReranker ready (model=%s)", model_name)

    def rerank(
        self, query: str, results: List[RetrievalResult], top_k: int
    ) -> List[RetrievalResult]:
        if not results:
            return []

        pairs = [(query, r.chunk.text) for r in results]
        scores = self._model.predict(pairs)

        ranked = sorted(
            zip(results, scores), key=lambda x: float(x[1]), reverse=True
        )
        reranked = [
            RetrievalResult(chunk=r.chunk, score=float(s), rank=i + 1)
            for i, (r, s) in enumerate(ranked[:top_k])
        ]

        logger.info(
            "Cross-encoder reranked %d -> %d results for query '%.40s...'",
            len(results),
            len(reranked),
            query,
        )
        return reranked
