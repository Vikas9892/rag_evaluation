"""Interactive RAG CLI: question -> retrieval -> prompt -> generation -> answer."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import TOP_K
from retrieval.retriever import Retriever
from generation.prompt_builder import PromptBuilder
from generation.generator import GroqGenerator

DIVIDER = "-" * 52


def _display_answer(response, retrieval_ms: float) -> None:
    print(f"\n{DIVIDER}")
    print("Answer\n")
    print(response.answer)

    print(f"\n{DIVIDER}")
    print("Sources\n")
    for result in response.sources:
        chunk_idx = result.chunk.metadata.get("chunk_index", "?")
        print(f"  {result.chunk.document_id}")
        print(f"  Chunk {chunk_idx}")
        print(f"  Score {result.score:.4f}")
        print()

    total_ms = retrieval_ms + response.latency_ms
    print(f"{DIVIDER}")
    print("Latency\n")
    print(f"  Retrieval  : {retrieval_ms:.0f} ms")
    print(f"  Generation : {response.latency_ms:.0f} ms")
    print(f"  Total      : {total_ms:.0f} ms")
    print(f"  Tokens     : {response.prompt_tokens}p + {response.completion_tokens}c")
    print(f"\n{DIVIDER}\n")


def main() -> None:
    print("Loading pipeline...", end=" ", flush=True)
    retriever = Retriever.from_disk()
    generator = GroqGenerator()
    builder = PromptBuilder()
    print("ready.\n")
    print("RAG QA  (type 'quit' to exit)")
    print(DIVIDER)

    while True:
        try:
            question = input("\nQuestion: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not question:
            continue
        if question.lower() == "quit":
            break

        print(f"\n{DIVIDER}")

        # --- Retrieval ---
        t0 = time.perf_counter()
        results = retriever.retrieve(question, top_k=TOP_K)
        retrieval_ms = (time.perf_counter() - t0) * 1000
        print(f"Retrieving...  Top {len(results)} chunks found")

        # --- Prompt ---
        print("Building prompt...")
        prompt = builder.build(question, results)

        # --- Generation ---
        print("Generating answer...")
        response = generator.generate(prompt, results)

        _display_answer(response, retrieval_ms)


if __name__ == "__main__":
    main()
