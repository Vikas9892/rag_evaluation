"""Hybrid retriever — dense (FAISS) + sparse (BM25) fused via RRF.

Reciprocal Rank Fusion (Cormack et al., 2009):
    score(d) = Σ  1 / (k + rank_i(d))
              i∈{dense, sparse}

k=60 is the constant from the original paper; it dampens the impact of
very-high-ranked documents so neither retriever can dominate completely.
"""

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

from config.logging_config import get_logger
from config.settings import FAISS_INDEX_FILE, METADATA_FILE, TOP_K
from chunking.chunk import Chunk

from corpora import DEFAULT_CORPUS_ID, CorpusNotFoundError, corpus_layout

from .bm25_store import BM25Store
from .pipeline import PipelineStage
from .ranking import RetrievalResult, RetrievalTrace, RetrieverMode, StageScore
from .retriever import Retriever

logger = get_logger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from .reranker import BaseReranker

_RRF_K = 60  # constant from the original RRF paper


def _default_reranker() -> "BaseReranker":
    """Imported lazily: sentence-transformers is heavy and only reranking needs it."""
    from .reranker import CrossEncoderReranker

    return CrossEncoderReranker()


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
        reranker: Optional["BaseReranker"] = None,
        reranker_factory: Optional[Callable[[], "BaseReranker"]] = None,
    ) -> None:
        self._dense = dense
        self._bm25 = bm25
        self._candidate_multiplier = candidate_multiplier
        self._reranker = reranker
        self._reranker_factory = reranker_factory

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_corpus(cls, corpus_id: str = DEFAULT_CORPUS_ID) -> "HybridRetriever":
        """Load one corpus into the same retrieval core the evaluation uses.

        There is deliberately no second implementation for uploaded documents:
        a workspace query and a benchmark run go through this class, so a
        measured configuration is the configuration users actually get.
        """
        layout = corpus_layout(corpus_id)
        if not layout.exists:
            raise CorpusNotFoundError(f"Corpus {corpus_id!r} has not been indexed")
        return cls.from_disk(
            index_path=layout.faiss_path, metadata_path=layout.metadata_path
        )

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
                corpus_id=r.get("corpus_id", DEFAULT_CORPUS_ID),
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
    # Corpus
    # ------------------------------------------------------------------

    def corpus_size(self) -> int:
        return self._bm25.ntotal

    def document_count(self) -> int:
        """Distinct source documents behind the indexed chunks."""
        return len({c.document_id for c in self._bm25._chunks})

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def _get_reranker(self):
        """Build the cross-encoder on first use.

        Constructing it downloads and loads a model, so a deployment that never
        asks for reranking never pays that cost.
        """
        if self._reranker is None:
            factory = self._reranker_factory or _default_reranker
            self._reranker = factory()
        return self._reranker

    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K,
        mode: RetrieverMode = "hybrid",
        reranker: bool = False,
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
        results, _ = self.retrieve_traced(
            query, top_k=top_k, mode=mode, reranker=reranker
        )
        return results

    def retrieve_traced(
        self,
        query: str,
        top_k: int = TOP_K,
        mode: RetrieverMode = "hybrid",
        reranker: bool = False,
    ) -> Tuple[List[RetrievalResult], List[PipelineStage]]:
        """Retrieve, and report which stages ran and what each cost.

        The stage list is what makes the pipeline diagram honest. It is produced
        here rather than inferred by the caller because only this method knows
        what it chose to run: a sparse-only query embeds nothing, so `embedding`
        is genuinely skipped, and that is not something a frontend could work
        out from a result set.
        """
        if mode == "dense":
            # Retrieve wider when reranking, so the reranker has candidates to
            # reorder. Handing it exactly top_k can only permute what the first
            # stage already chose.
            width = top_k * self._candidate_multiplier if reranker else top_k
            results, stages = self._dense.retrieve_traced(query, top_k=width)
            return self._maybe_rerank(query, results, stages, top_k, reranker)

        if mode == "sparse":
            t0 = time.perf_counter()
            width = top_k * self._candidate_multiplier if reranker else top_k
            results = self._bm25.search(query, top_k=width)
            sparse_ms = (time.perf_counter() - t0) * 1000
            return self._maybe_rerank(
                query,
                results,
                [
                    # BM25 matches terms, so nothing is embedded. This is the
                    # one stage the live pipeline genuinely skips by request.
                    PipelineStage.skipped("embedding"),
                    PipelineStage(
                        name="sparse",
                        status="ok",
                        latency_ms=sparse_ms,
                        candidates_in=self._bm25.ntotal,
                        candidates_out=len(results),
                    ),
                ],
                top_k,
                reranker,
            )

        # Fusion needs a wider window than it returns: a chunk ranked 30th by
        # one retriever and 2nd by the other should still surface.
        candidates = top_k * self._candidate_multiplier

        dense_results, dense_pipeline = self._dense.retrieve_traced(
            query, top_k=candidates
        )

        t_sparse = time.perf_counter()
        bm25_results = self._bm25.search(query, top_k=candidates)
        sparse_ms = (time.perf_counter() - t_sparse) * 1000

        t_fusion = time.perf_counter()

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

        fusion_ms = (time.perf_counter() - t_fusion) * 1000

        logger.info(
            "Hybrid query '%.40s...' -> %d result(s) (dense=%d, bm25=%d)",
            query,
            len(results),
            len(dense_results),
            len(bm25_results),
        )

        stages = [
            *dense_pipeline,
            PipelineStage(
                name="sparse",
                status="ok",
                latency_ms=sparse_ms,
                candidates_in=self._bm25.ntotal,
                candidates_out=len(bm25_results),
            ),
            PipelineStage(
                name="fusion",
                status="ok",
                latency_ms=fusion_ms,
                # The union, not the sum: a chunk both retrievers found is one
                # candidate, and double-counting it would overstate the funnel.
                candidates_in=len(rrf_scores),
                candidates_out=len(results),
            ),
        ]
        return self._maybe_rerank(query, results, stages, top_k, reranker)

    def _maybe_rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        stages: List[PipelineStage],
        top_k: int,
        reranker: bool,
    ) -> Tuple[List[RetrievalResult], List[PipelineStage]]:
        """Run the cross-encoder if asked, and report the stage either way.

        When it does not run, no reranker stage is reported at all and
        `fill_skipped` marks it skipped — which is what the diagram greys out.
        Reporting a zero-latency "ok" stage would claim it ran.
        """
        if not reranker:
            return results[:top_k], stages

        t0 = time.perf_counter()
        reranked = self._get_reranker().rerank(query, results, top_k=top_k)
        rerank_ms = (time.perf_counter() - t0) * 1000

        return reranked, [
            *stages,
            PipelineStage(
                name="reranker",
                status="ok",
                latency_ms=rerank_ms,
                candidates_in=len(results),
                candidates_out=len(reranked),
            ),
        ]
