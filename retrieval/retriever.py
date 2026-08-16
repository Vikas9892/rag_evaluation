import json
import time
from pathlib import Path
from typing import List, Tuple

from config.logging_config import get_logger
from config.settings import FAISS_INDEX_FILE, METADATA_FILE, TOP_K
from chunking.chunk import Chunk
from embeddings.embedder import Embedder, shared_embedder

from corpora import DEFAULT_CORPUS_ID, CorpusNotFoundError, corpus_layout

from .faiss_store import FAISSStore
from .pipeline import PipelineStage
from .ranking import RetrievalResult, RetrievalTrace, StageScore

logger = get_logger(__name__)


class Retriever:
    """End-to-end retrieval: question -> embedding -> FAISS -> ranked Chunks.

    Composes Embedder and FAISSStore.  Metadata is loaded once at construction
    and kept in memory for O(1) index lookups — the index alignment guarantee
    from Phase 3 (vectors[i] corresponds to metadata[i]) is what makes this safe.
    """

    def __init__(
        self,
        store: FAISSStore,
        metadata: List[dict],
        embedder: Embedder | None = None,
    ) -> None:
        self._store = store
        self._metadata = metadata
        # Shared rather than constructed: one service is cached per corpus, and
        # each building its own model meant N copies of identical weights.
        self._embedder = embedder if embedder is not None else shared_embedder()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_corpus(
        cls, corpus_id: str = DEFAULT_CORPUS_ID, embedder: Embedder | None = None
    ) -> "Retriever":
        """Load one corpus's index.

        Raises CorpusNotFoundError rather than FileNotFoundError so a caller can
        tell "this collection was never indexed" from "the disk is broken".
        """
        layout = corpus_layout(corpus_id)
        if not layout.exists:
            raise CorpusNotFoundError(f"Corpus {corpus_id!r} has not been indexed")
        return cls.from_disk(
            index_path=layout.faiss_path,
            metadata_path=layout.metadata_path,
            embedder=embedder,
        )

    @classmethod
    def from_disk(
        cls,
        index_path: Path | str = FAISS_INDEX_FILE,
        metadata_path: Path | str = METADATA_FILE,
        embedder: Embedder | None = None,
    ) -> "Retriever":
        """Load index + metadata from standard paths and return a ready Retriever."""
        store = FAISSStore.load(index_path)
        records = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        logger.info("Retriever ready: %d indexed chunks", store.ntotal)
        return cls(store=store, metadata=records, embedder=embedder)

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = TOP_K) -> List[RetrievalResult]:
        """Embed query, search FAISS, return RetrievalResult list sorted by score."""
        results, _ = self.retrieve_traced(query, top_k=top_k)
        return results

    def retrieve_traced(
        self, query: str, top_k: int = TOP_K
    ) -> Tuple[List[RetrievalResult], List[PipelineStage]]:
        """Retrieve, and report the embedding and search stages separately.

        Embedding is timed apart from the search because they fail and scale for
        different reasons: one is a model forward pass whose cost is fixed per
        query, the other grows with the index. A single "retrieval" number hides
        which of the two a slow query was waiting on.

        Indices returned by FAISS are guaranteed to align with self._metadata
        because both were written together by VectorStorage.save() in Phase 3.
        """
        t0 = time.perf_counter()
        query_vector = self._embedder.embed(query)
        embedding_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        scores, indices = self._store.search(query_vector, top_k=top_k)

        results: List[RetrievalResult] = []
        for rank, (score, idx) in enumerate(zip(scores, indices), start=1):
            if idx < 0:  # FAISS sentinel for unfilled slots
                continue
            rec = self._metadata[idx]
            chunk = Chunk(
                chunk_id=rec["chunk_id"],
                document_id=rec["document_id"],
                text=rec["text"],
                start_char=rec["start_char"],
                end_char=rec["end_char"],
                metadata=rec["metadata"],
                corpus_id=rec.get("corpus_id", DEFAULT_CORPUS_ID),
            )
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=float(score),
                    rank=rank,
                    # This retriever *is* the dense stage, so it records itself.
                    # A caller that fuses will add the other stages around it
                    # rather than recomputing what this one already knows.
                    trace=RetrievalTrace(dense=StageScore(score=float(score), rank=rank)),
                )
            )

        search_ms = (time.perf_counter() - t1) * 1000

        if results:
            logger.info(
                "Query '%.40s...' -> %d result(s), top score: %.3f",
                query,
                len(results),
                results[0].score,
            )
        else:
            logger.info("Query '%.40s...' -> no results", query)

        stages = [
            PipelineStage(
                name="embedding",
                status="ok",
                latency_ms=embedding_ms,
                # A question is not a candidate set; counting it as one would
                # put a meaningless "1 → 1" on the diagram.
                candidates_in=None,
                candidates_out=None,
            ),
            PipelineStage(
                name="dense",
                status="ok",
                latency_ms=search_ms,
                candidates_in=self._store.ntotal,
                candidates_out=len(results),
            ),
        ]
        return results, stages
