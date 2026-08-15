# Baseline — before the workspace/lab split

Captured at `fdb3809`, before any Phase 1+ work. This file exists so the
"preserve current evaluation" requirement is checkable rather than asserted:
every number below is re-measurable with the commands given.

## Build and tests

| Check | Result | Command |
|---|---|---|
| Python tests | **453 passed, 0 failed** | `pytest` |
| Python coverage | **91%** (gate: 85%) | `pytest --cov=.` |
| Frontend tests | **224 passed** (18 files) | `cd frontend && npm test` |
| Typecheck | pass | `npm run typecheck` |
| Lint | pass | `npm run lint` |
| Build | pass, 9 static routes | `npm run build` |
| CI | green on 3.11 and 3.12 | GitHub Actions |

## Corpus and dataset

| | Value |
|---|---|
| Indexed chunks | 148 |
| Source documents | 8 |
| Labelled questions | 53 |
| Chunk size / overlap / minimum | 250 / 50 / 50 |
| Embedding model | BAAI/bge-small-en-v1.5 (384-dim) |
| Default retriever | dense |

## Evaluation — dense, top-5, reranker off

The configuration the API serves by default.

| Metric | Value |
|---|---|
| Precision@5 | 0.2000 |
| Recall@5 | 0.9623 |
| Hit rate | 0.9623 |
| MRR | 0.8780 |
| Avg retrieval latency | 49.6 ms |

Reproduce: `GET /evaluation?top_k=5&retriever=dense`

The full 18-configuration matrix is in [benchmark_report.md](benchmark_report.md).

## Existing architecture

Already present and to be preserved, not rebuilt:

- **Ingestion** — `ingestion/`: `BaseParser` with PDF, TXT and Markdown
  implementations; `TextCleaner`; `DocumentLoader` over a directory.
- **Chunking** — `chunking/splitter.py`, heading-aware with sub-threshold merge.
- **Embedding** — `embeddings/`: `Embedder`, `EmbeddingService`, `VectorStorage`.
  **`VectorStorage.append()` already supports incremental indexing**, which is
  what makes per-document upload viable without a full rebuild.
- **Retrieval** — `retrieval/`: `FAISSStore` (dense), `BM25Store` (sparse),
  `HybridRetriever` (RRF, k=60), `CrossEncoderReranker` (opt-in),
  `RetrievalTrace` per-stage attribution, `PipelineStage` per-stage timings.
- **Generation** — `generation/`: `PromptBuilder`, `GroqGenerator`, abstention
  contract.
- **Evaluation** — `evaluation/`: metrics, content-anchored ground truth,
  retrieval and generation evaluators, benchmark runner, report generator.
- **API** — `api/`: query, stream, health, config, evaluation, prometheus
  routers; token-bucket rate limiting; CORS allowlist.
- **Frontend** — `frontend/`: Next.js 16 App Router, six routes, TanStack Query,
  Base UI + Tailwind, typed client generated from the OpenAPI schema.

## What does not exist yet

- No document upload endpoint. The corpus is built offline by
  `scripts/build_embeddings.py` and `scripts/build_index.py`.
- No job queue or worker. Nothing runs asynchronously.
- No corpus namespace. There is exactly one index, shared by everything.
- No per-document lifecycle, status, or deletion.
- No dark mode.
