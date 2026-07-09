"""
Measure per-stage latency for the RAG pipeline and print a summary table.

Run from the project root:
    python scripts/benchmark_performance.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import statistics

import numpy as np

REPS = 20  # iterations for each latency measurement
QUERIES = [
    "What is machine learning?",
    "How does attention work in transformers?",
    "What are the main components of a RAG pipeline?",
    "Explain the difference between precision and recall.",
    "What is FAISS and how does it work?",
]

DIVIDER = "-" * 52


def _fmt(ms: float) -> str:
    return f"{ms:>8.1f} ms"


def _measure(fn, reps: int) -> dict:
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "mean": statistics.mean(times),
        "p50": statistics.median(times),
        "p95": sorted(times)[int(len(times) * 0.95)],
        "min": min(times),
        "max": max(times),
    }


def main() -> None:
    results: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 1. Embedder (single + batch)
    # ------------------------------------------------------------------
    print("Loading embedder...", end=" ", flush=True)
    from embeddings.embedder import Embedder
    embedder = Embedder()
    print("done.")

    results["Single embed"] = _measure(
        lambda: embedder.embed(QUERIES[0]), reps=REPS
    )
    batch = QUERIES * 4  # 20 texts
    results["Batch embed (20)"] = _measure(
        lambda: embedder.embed_many(batch), reps=max(REPS // 2, 5)
    )
    results["Per-chunk (batch/20)"] = {
        k: v / 20 for k, v in results["Batch embed (20)"].items()
    }

    # ------------------------------------------------------------------
    # 2. FAISS retrieval (requires built index)
    # ------------------------------------------------------------------
    from config.settings import FAISS_INDEX_FILE, METADATA_FILE

    if FAISS_INDEX_FILE.exists() and METADATA_FILE.exists():
        print("Loading retriever...", end=" ", flush=True)
        from retrieval.retriever import Retriever
        retriever = Retriever.from_disk()
        print(f"done ({retriever._store.ntotal} vectors).")

        for q in QUERIES[:3]:
            retriever.retrieve(q, top_k=5)  # warm up

        results["FAISS retrieve (top-5)"] = _measure(
            lambda: retriever.retrieve(QUERIES[0], top_k=5), reps=REPS
        )
    else:
        print("FAISS index not found — skipping retrieval benchmark.")
        print("Run: python scripts/chunk_documents.py && python scripts/embed_chunks.py")

    # ------------------------------------------------------------------
    # 3. BM25 (pure Python, always available)
    # ------------------------------------------------------------------
    import json
    if METADATA_FILE.exists():
        records = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        from chunking.chunk import Chunk
        from retrieval.bm25_store import BM25Store
        chunks = [
            Chunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                text=r["text"],
                start_char=r["start_char"],
                end_char=r["end_char"],
            )
            for r in records
        ]
        bm25 = BM25Store(chunks)
        results["BM25 retrieve (top-5)"] = _measure(
            lambda: bm25.search(QUERIES[0], top_k=5), reps=REPS
        )

    # ------------------------------------------------------------------
    # Print summary table
    # ------------------------------------------------------------------
    print()
    print(DIVIDER)
    print(f"{'Stage':<28}  {'Mean':>10}  {'P95':>10}  {'Min':>10}")
    print(DIVIDER)
    for stage, stats in results.items():
        print(
            f"{stage:<28}  {_fmt(stats['mean'])}  {_fmt(stats['p95'])}  {_fmt(stats['min'])}"
        )
    print(DIVIDER)
    print()

    # Save to JSON for README embedding
    import json as _json
    out = Path(__file__).resolve().parent.parent / "reports" / "benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(
        _json.dumps({k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in results.items()},
                    indent=2),
        encoding="utf-8",
    )
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
