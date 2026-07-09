import json
from pathlib import Path
from typing import List

from config.logging_config import get_logger
from config.settings import FAISS_INDEX_FILE, METADATA_FILE, TOP_K
from chunking.chunk import Chunk
from embeddings.embedder import Embedder

from .faiss_store import FAISSStore
from .ranking import RetrievalResult

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
        self._embedder = embedder if embedder is not None else Embedder()

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

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
        """Embed query, search FAISS, return RetrievalResult list sorted by score.

        Indices returned by FAISS are guaranteed to align with self._metadata
        because both were written together by VectorStorage.save() in Phase 3.
        """
        query_vector = self._embedder.embed(query)
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
            )
            results.append(RetrievalResult(chunk=chunk, score=float(score), rank=rank))

        if results:
            logger.info(
                "Query '%.40s...' -> %d result(s), top score: %.3f",
                query,
                len(results),
                results[0].score,
            )
        else:
            logger.info("Query '%.40s...' -> no results", query)

        return results
