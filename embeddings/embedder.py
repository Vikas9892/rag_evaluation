from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from config.logging_config import get_logger
from config.settings import BATCH_SIZE, DEVICE, EMBEDDING_MODEL

logger = get_logger(__name__)


class Embedder:
    """Wraps a SentenceTransformer model.

    The model is loaded exactly once at construction time and reused for every
    subsequent call.  Never reload per-request — that turns a 20 ms operation
    into a 3+ second one.
    """

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        device: str = DEVICE,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model = SentenceTransformer(model_name, device=device)
        self.dimension: int = self._model.get_embedding_dimension()
        logger.info(
            "Loaded embedding model: %s (dim=%d, device=%s)",
            model_name,
            self.dimension,
            device,
        )

    def embed(self, text: str) -> np.ndarray:
        """Embed a single string → 1-D float32 array of shape (dim,)."""
        return self._model.encode(text, convert_to_numpy=True, show_progress_bar=False)

    def embed_many(
        self,
        texts: List[str],
        batch_size: int = BATCH_SIZE,
    ) -> np.ndarray:
        """Embed a list of strings → 2-D float32 array of shape (n, dim).

        Returns an empty (0, dim) array when texts is empty so callers never
        need to special-case the empty input.
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        return self._model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
