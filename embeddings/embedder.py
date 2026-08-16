from functools import lru_cache
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


@lru_cache(maxsize=4)
def shared_embedder(
    model_name: str = EMBEDDING_MODEL, device: str = DEVICE
) -> Embedder:
    """The process's embedding model, loaded once.

    bge-small is ~130 MB of weights and several seconds to load. Every retriever
    and the indexing worker used to construct their own, so a process serving
    eight corpora held eight identical copies of the same model — around a
    gigabyte of resident memory to do exactly what one copy does.

    Keyed by model and device rather than a bare singleton, so a caller that
    genuinely wants a different model still gets one; the cache is bounded
    because those are the only axes that can vary.

    Shared across threads: the indexing worker embeds while queries embed, and
    SentenceTransformer inference is read-only over the model weights. That is
    the same assumption every server that loads one model and serves concurrent
    requests makes. Construct `Embedder()` directly to opt out.
    """
    return Embedder(model_name=model_name, device=device)
