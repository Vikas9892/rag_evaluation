"""Build a FAISS index from the stored vectors and save it to disk."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import get_logger
from embeddings.storage import VectorStorage
from retrieval.faiss_store import FAISSStore

logger = get_logger(__name__)


def main() -> None:
    vectors, metadata = VectorStorage().load()
    logger.info("Loaded %d vectors (dim=%d)", len(vectors), vectors.shape[1])

    store = FAISSStore(dimension=vectors.shape[1])
    store.add(vectors)
    store.save()

    print("\n--- Index build complete ---")
    print(f"  Vectors indexed : {store.ntotal}")
    print(f"  Dimension       : {vectors.shape[1]}")
    print(f"  Saved to        : index/faiss.index")


if __name__ == "__main__":
    main()
