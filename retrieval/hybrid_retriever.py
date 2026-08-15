"""Hybrid retriever — dense (FAISS) + sparse (BM25) fused via RRF.

Reciprocal Rank Fusion (Cormack et al., 2009):
    score(d) = Σ  1 / (k + rank_i(d))
              i∈{dense, sparse}

k=60 is the constant from the original paper; it dampens the impact of
very-high-ranked documents so neither retriever can dominate completely.
"""
import json
from pathlib import Path
from typing import List, Optional

from config.logging_config import get_logger
from config.settings import FAISS_INDEX_FILE, METADATA_FILE, TOP_K
from chunking.chunk import Chunk

from .bm25_store import BM25Store
from .faiss_store import FAISSStore
from .ranking import RetrievalResult, RetrievalTrace, RetrieverMode, StageScore
from .retriever import Retriever

logger = get_logger(__name__)

_RRF_K = 60  # constant from the original RRF paper


class HybridRetriever:
    """Combines dense and sparse retrieval with Reciprocal Rank Fusion.

    Typical usage
    -------------
    >>> retriever = HybridRetriever.from_disk()
    >>> results = retriever.retrieve("what is the Eiffel Tower?", top_k=5)
    """

    def __init__(
        self,
        dense: Retriever,
        bm25: BM25Store,
        candidate_multiplier: int = 4,
    ) -> None:
        self._dense = dense
        self._bm25 = bm25
        self._candidate_multiplier = candidate_multiplier

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_disk(
        cls,
        index_path: Path | str = FAISS_INDEX_FILE,
        metadata_path: Path | str = METADATA_FILE,
    ) -> "HybridRetriever":
        dense = Retriever.from_disk(index_path=index_path, metadata_path=metadata_path)
        records = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        chunks = [
            Chunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                text=r["text"],
                start_char=r["start_char"],
                end_char=r["end_char"],
                metadata=r["metadata"],
            )
            for r in records
        ]
        bm25 = BM25Store(chunks)
        logger.info(
            "HybridRetriever ready: %d dense vectors, %d BM25 docs",
            dense._store.ntotal,
            bm25.ntotal,
        )
        return cls(dense=dense, bm25=bm25)

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K,
        mode: RetrieverMode = "hybrid",
    ) -> List[RetrievalResult]:
        """Retrieve top_k chunks, recording what each stage contributed.

        `mode` selects the strategy: "dense" and "sparse" run one stage alone,
        "hybrid" fuses both with RRF. Comparing them is the point of the
        platform, so it is a per-request choice rather than a deployment one.

        Every result carries a trace of the stages that ranked it. Fusion used
        to collapse two rankings into one number and throw the inputs away,
        which made it impossible to answer the question the retrieval table
        exists for: *which* retriever found this, and where did the other one
        put it?
        """
        if mode == "dense":
            return self._dense.retrieve(query, top_k=top_k)
        if mode == "sparse":
            return self._bm25.search(query, top_k=top_k)

        # Fusion needs a wider window than it returns: a chunk ranked 30th by
        # one retriever and 2nd by the other should still surface.
        candidates = top_k * self._candidate_multiplier

        dense_results = self._dense.retrieve(query, top_k=candidates)
        bm25_results = self._bm25.search(query, top_k=candidates)

        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}
        dense_stages: dict[str, StageScore] = {}
        sparse_stages: dict[str, StageScore] = {}

        for rank, result in enumerate(dense_results, start=1):
            cid = result.chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
            chunk_map[cid] = result.chunk
            dense_stages[cid] = StageScore(score=result.score, rank=rank)

        for rank, result in enumerate(bm25_results, start=1):
            cid = result.chunk.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
            chunk_map[cid] = result.chunk
            sparse_stages[cid] = StageScore(score=result.score, rank=rank)

        sorted_ids = sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)
        results = [
            RetrievalResult(
                chunk=chunk_map[cid],
                score=round(rrf_scores[cid], 6),
                rank=i + 1,
                trace=RetrievalTrace(
                    # Absent when that retriever did not surface this chunk
                    # within its candidate window — not when it scored zero.
                    dense=dense_stages.get(cid),
                    sparse=sparse_stages.get(cid),
                    fused=StageScore(score=round(rrf_scores[cid], 6), rank=i + 1),
                ),
            )
            for i, cid in enumerate(sorted_ids[:top_k])
        ]

        logger.info(
            "Hybrid query '%.40s...' -> %d result(s) (dense=%d, bm25=%d)",
            query,
            len(results),
            len(dense_results),
            len(bm25_results),
        )
        return results
