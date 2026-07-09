from pathlib import Path
from typing import Tuple

import faiss
import numpy as np

from config.logging_config import get_logger
from config.settings import FAISS_INDEX_FILE

logger = get_logger(__name__)


class FAISSStore:
    """Manages the FAISS index lifecycle: create, populate, save, load, search.

    This class knows nothing about Chunks, embeddings, or metadata — it
    operates purely on float32 vectors.  That separation means the index
    can be swapped (e.g. IVF, HNSW) without touching any other module.

    Index type: IndexFlatIP (exact inner-product search).
    Vectors are L2-normalised before add() and search(), so inner product
    equals cosine similarity.  BGE models are trained with cosine similarity,
    so this gives correct ranking.  IndexFlatL2 would measure Euclidean
    distance, which is appropriate for other model families but not BGE.
    """

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self._index: faiss.IndexFlatIP = faiss.IndexFlatIP(dimension)

    # ------------------------------------------------------------------
    # Mutating operations
    # ------------------------------------------------------------------

    def add(self, vectors: np.ndarray) -> None:
        """L2-normalise then insert vectors into the index.

        Raises ValueError for shape or dtype mismatches so the caller gets a
        clear message instead of a cryptic FAISS RuntimeError.
        """
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise ValueError(
                f"Expected shape (n, {self.dimension}), got {vectors.shape}"
            )
        normed = vectors.copy().astype(np.float32)
        faiss.normalize_L2(normed)
        self._index.add(normed)
        logger.info(
            "Added %d vector(s) to FAISS index (total: %d)",
            len(vectors),
            self._index.ntotal,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(
        self, query_vector: np.ndarray, top_k: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (scores, indices) for the top_k nearest neighbours.

        - scores  : float32 array, cosine similarities in [-1, 1], descending
        - indices : int64 array, row indices into the original add() call

        Edge cases handled gracefully:
        - empty index      → returns two empty arrays
        - top_k > ntotal   → returns however many vectors exist
        - top_k < 1        → raises ValueError
        """
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")
        if self._index.ntotal == 0:
            return np.empty(0, dtype=np.float32), np.empty(0, dtype=np.int64)

        q = query_vector.reshape(1, -1).astype(np.float32).copy()
        faiss.normalize_L2(q)

        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(q, k)
        return scores[0], indices[0]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path | str = FAISS_INDEX_FILE) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(path))
        logger.info(
            "Saved FAISS index (%d vectors) to %s", self._index.ntotal, path
        )

    @classmethod
    def load(cls, path: Path | str = FAISS_INDEX_FILE) -> "FAISSStore":
        """Load a persisted index and wrap it in a FAISSStore instance."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"FAISS index not found: {path}")
        raw = faiss.read_index(str(path))
        store = cls(dimension=raw.d)
        store._index = raw  # replace the freshly created empty index
        logger.info(
            "Loaded FAISS index with %d vectors (dim=%d) from %s",
            raw.ntotal,
            raw.d,
            path,
        )
        return store

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def ntotal(self) -> int:
        return self._index.ntotal
