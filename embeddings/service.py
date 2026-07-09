import time
from typing import List

import numpy as np

from config.logging_config import get_logger
from config.settings import BATCH_SIZE
from chunking.chunk import Chunk

from .embedder import Embedder

logger = get_logger(__name__)


class EmbeddingService:
    """Orchestrates batch embedding for a collection of Chunk objects.

    Keeps the Embedder (model I/O) decoupled from batch-processing logic,
    timing, and logging — matching the same single-responsibility split used
    in the ingestion and chunking layers.
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self.embedder = embedder if embedder is not None else Embedder()
        self.batch_size = batch_size

    def embed_chunks(self, chunks: List[Chunk]) -> np.ndarray:
        """Embed all chunks and return a (n, dim) float32 matrix.

        Row i of the returned array corresponds to chunks[i].  The caller can
        rely on this index alignment when building the metadata mapping.
        """
        if not chunks:
            logger.warning("embed_chunks called with empty chunk list")
            return np.empty((0, self.embedder.dimension), dtype=np.float32)

        texts = [c.text for c in chunks]
        t0 = time.perf_counter()
        vectors = self.embedder.embed_many(texts, batch_size=self.batch_size)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Embedded %d chunks | avg %.1f ms/chunk",
            len(chunks),
            elapsed_ms / len(chunks),
        )
        return vectors
