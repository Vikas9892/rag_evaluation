"""End-to-end pipeline: ingest -> chunk -> embed -> save."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import get_logger
from config.settings import RAW_DATA_DIR
from ingestion.loader import DocumentLoader
from chunking.splitter import DocumentSplitter
from embeddings.service import EmbeddingService
from embeddings.storage import VectorStorage

logger = get_logger(__name__)


def main() -> None:
    docs = DocumentLoader(RAW_DATA_DIR).load()
    logger.info("Loaded %d document(s)", len(docs))

    chunks = DocumentSplitter().split_many(docs)
    logger.info("Generated %d chunks", len(chunks))

    service = EmbeddingService()
    vectors = service.embed_chunks(chunks)
    logger.info("Embedded %d chunks", len(chunks))

    VectorStorage().save(vectors, chunks)

    print("\n--- Embedding pipeline complete ---")
    print(f"  Documents : {len(docs)}")
    print(f"  Chunks    : {len(chunks)}")
    print(f"  Vectors   : {vectors.shape}")
    print(f"  Saved to  : index/")


if __name__ == "__main__":
    main()
