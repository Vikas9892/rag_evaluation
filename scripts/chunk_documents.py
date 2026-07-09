"""Entry point: load all documents from data/raw/, chunk them, and print a summary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import get_logger
from config.settings import RAW_DATA_DIR
from ingestion.loader import DocumentLoader
from chunking.splitter import DocumentSplitter

logger = get_logger(__name__)


def main() -> None:
    loader = DocumentLoader(RAW_DATA_DIR)
    docs = loader.load()
    logger.info("Loaded %d document(s)", len(docs))

    splitter = DocumentSplitter()
    per_doc: dict[str, int] = {}
    all_chunks = []

    for doc in docs:
        chunks = splitter.split(doc)
        per_doc[doc.id] = len(chunks)
        all_chunks.extend(chunks)

    total = len(all_chunks)
    logger.info("Total chunks: %d", total)

    print(f"\n--- Chunking complete: {total} chunk(s) from {len(docs)} document(s) ---")
    for doc_id, count in per_doc.items():
        print(f"  {doc_id} -> {count} chunks")


if __name__ == "__main__":
    main()
