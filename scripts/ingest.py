"""Entry point: ingest all documents from data/raw/ and print a summary."""
import sys
from pathlib import Path

# make project root importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import RAW_DATA_DIR
from ingestion.loader import DocumentLoader


def main():
    loader = DocumentLoader(RAW_DATA_DIR)
    docs = loader.load()
    print(f"\n--- Ingestion complete: {len(docs)} document(s) loaded ---")
    for doc in docs:
        print(f"  [{doc.metadata.get('type', '?').upper()}] {doc.id} "
              f"({len(doc.text)} chars)")


if __name__ == "__main__":
    main()
