# ADR 004 — Vector Index (FAISS IndexFlatIP)

**Status:** Accepted  
**Date:** 2026-07

---

## Context

The retrieval layer needs a vector index that supports cosine-similarity search on 384-
dimensional float32 vectors.  The index must load from disk in < 1 second and fit in
Lambda memory.  At the current scale (< 10 000 chunks), both exact and approximate
search are feasible.

## Decision

Use `faiss.IndexFlatIP` (exact inner-product search).  L2-normalise all vectors before
`add()` and `search()` so that inner product equals cosine similarity.

## Rationale

**Why exact over approximate (IVF, HNSW)?**  At < 10 000 vectors, `IndexFlatIP.search()`
takes < 1 ms on CPU — the latency is dominated by network I/O and the LLM call, not
FAISS.  Approximate indexes (IVF, HNSW) trade recall for speed.  We pay no speed
penalty at this scale, so there is no reason to accept reduced recall.

**Why inner product instead of L2?**  BGE models are trained with cosine loss.  After
L2 normalisation, ‖v‖ = 1 for all vectors, so `IP(a, b) = aᵀb = cos(a, b)`.
`IndexFlatL2` would measure Euclidean distance, which ranks differently and is not what
the model was trained to optimise.

**Persistence:**  FAISS provides `faiss.write_index` / `faiss.read_index`.  A 10 000-
vector index serialises to ~15 MB in < 50 ms.

## Consequences

- Exact search scales to ~100 000 vectors before latency becomes noticeable (>10 ms).
  Beyond that, switch to `IndexIVFFlat` (partitioned) or `IndexHNSWFlat` (graph).
- `IndexFlatIP` does not support deletion.  Rebuilding is required to remove vectors.
  For incremental additions without deletion, `index.add()` works directly.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| Chroma / Qdrant | Extra service dependency; overkill at this scale |
| Annoy | Read-only index; cannot append after build |
| IndexHNSWFlat | Approximate recall; unnecessary at < 10 K vectors |
| IndexIVFFlat | Requires training step; more tuning for marginal gain |
| pgvector (Postgres) | Requires a database deployment; too heavy for Lambda |
