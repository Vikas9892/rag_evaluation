"""Interactive CLI: embed a query, search the FAISS index, display ranked results."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import TOP_K
from retrieval.retriever import Retriever

DIVIDER = "-" * 52


def _truncate(text: str, limit: int = 350) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def main() -> None:
    print("Loading index...", end=" ", flush=True)
    retriever = Retriever.from_disk()
    print("ready.\n")

    print("RAG Retrieval Search  (type 'quit' to exit)")
    print(DIVIDER)

    while True:
        try:
            query = input("\nEnter question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not query:
            continue
        if query.lower() == "quit":
            break

        results = retriever.retrieve(query, top_k=TOP_K)

        if not results:
            print("No results found.")
            continue

        print(f"\nTop {len(results)} Results\n")
        for result in results:
            print(f"{result.rank}. {result.chunk.document_id}")
            print(f"   Score: {result.score:.4f}")
            print()
            for line in _truncate(result.chunk.text).splitlines():
                print(f"   {line}")
            print(f"\n{DIVIDER}")


if __name__ == "__main__":
    main()
