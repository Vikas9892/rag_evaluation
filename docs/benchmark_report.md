# Benchmark Report

**Corpus:** 148 chunks across 8 documents · **Dataset:** 53 labelled questions
**Configurations:** 18 — retriever (dense, sparse, hybrid) × top-K (3, 5, 10) × reranker (off, on)
**Measured:** 2026-08-15, on the index built by `scripts/build_index.py` at that commit

Regenerate with `GET /benchmarks`. Every number below came from that endpoint;
none are hand-copied estimates.

---

## Headline

**Reranking is the largest single lever, and it costs an order of magnitude in
latency.** Every one of the nine best configurations by MRR uses the
cross-encoder. Without it, dense retrieval leads.

| Configuration | MRR | Recall | Hit rate |
|---|---|---|---|
| dense · top-5 · **reranked** | **0.914** | 0.981 | 0.981 |
| hybrid · top-5 · reranked | 0.888 | 0.934 | 0.943 |
| sparse · top-5 · reranked | 0.888 | 0.924 | 0.943 |
| dense · top-5 | 0.878 | 0.962 | 0.962 |
| hybrid · top-5 | 0.848 | 0.934 | 0.943 |
| sparse · top-5 | 0.715 | 0.811 | 0.830 |

## Reranking helps most where the first stage is weakest

| Retriever @5 | without | with | gain |
|---|---|---|---|
| sparse | 0.715 | 0.888 | **+0.173** |
| hybrid | 0.848 | 0.888 | +0.041 |
| dense | 0.878 | 0.914 | +0.036 |

A cross-encoder reorders whatever candidates it is given, so its value is
bounded by what the first stage recalled. Sparse retrieval recalls adequately
and ranks badly, which is exactly the shape a reranker repairs. Dense already
ranks well, so there is less left to fix.

The corollary matters for architecture: **with reranking on, the choice of
retriever nearly stops mattering** — 0.914, 0.888 and 0.888 across the three.
If the reranker is affordable, first-stage tuning is largely wasted effort.

## Dense beats hybrid, and fusion is the reason

Without reranking, at every top-K:

| top-K | dense | hybrid | sparse |
|---|---|---|---|
| 3 | **0.865** | 0.849 | 0.711 |
| 5 | **0.878** | 0.848 | 0.715 |
| 10 | **0.878** | 0.848 | 0.728 |

Reciprocal Rank Fusion gives each retriever an equal vote. When one is
substantially worse — sparse trails dense by 0.16 here — fusion drags the
combined ranking below its own better half. Hybrid retrieval is not free
insurance; it is an average, and averaging with something worse makes things
worse.

**This changed the default.** The live default was hybrid; it is now dense.

An earlier run on the 19-chunk corpus showed a larger gap (dense 1.000 against
hybrid 0.913). That corpus was too small to trust — MRR of 1.000 means the task
was trivial, not that retrieval was perfect. The 148-chunk result is smaller and
more believable, and points the same way.

## Precision@K is arithmetic, not a grade

| top-K | Precision@K (dense) |
|---|---|
| 3 | 0.315 |
| 5 | 0.200 |
| 10 | 0.100 |

Precision@K falls as K rises by construction: most questions have one relevant
chunk, so retrieving ten divides the same single hit across ten slots. It halves
from K=5 to K=10 almost exactly, which is the signature of a fixed numerator.

Read **Recall** and **MRR** when comparing across K. Precision@K is only
comparable at fixed K.

## Latency

| Configuration | avg retrieval |
|---|---|
| sparse · top-5 | 0.9 ms |
| hybrid · top-5 | 41 ms |
| dense · top-5 | 49 ms |
| reranked (any) | 130–1050 ms |

Dense and hybrid are dominated by the embedding model's forward pass — the
pipeline trace attributes ~99% of non-reranked retrieval latency to embedding,
not to the index. Sparse needs no embedding at all, which is why it is two
orders of magnitude faster.

**The reranked latencies in this run are not trustworthy for comparison.** The
cross-encoder loads lazily on first use, so whichever reranked cell ran first
absorbed the model load. The honest summary is "reranking costs hundreds of
milliseconds", not the specific per-cell figures.

## What this says about the default

Generation costs roughly 300–600 ms on this deployment. Against that:

- dense without reranking: **0.878 MRR at ~49 ms**
- dense with reranking: 0.914 MRR at several hundred ms

Paying a large fraction of the total response time for +0.036 MRR is a poor
trade for an interactive query, so the default is dense without reranking. The
reranker remains available per request (`"reranker": true`) and is swept in
every benchmark run, so the trade-off is re-measurable rather than assumed.

## Caveats

- 53 questions is small. Differences of 0.02–0.04 MRR are directional, not
  conclusive.
- The corpus is authored technical notes on eight CS topics. Results may not
  transfer to prose, tables, or multilingual text.
- Ground truth is one to two chunks per question, which is what caps
  Precision@K. A dataset with more relevant chunks per question would make that
  metric informative rather than mechanical.
- Every figure is retrieval-only. Generation quality is not measured here.
