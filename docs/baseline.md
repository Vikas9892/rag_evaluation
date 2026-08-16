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

---

## Verification after the workspace/lab work

The point of the snapshot above. Re-measured on the same corpus and the same
labelled dataset, with the upload pipeline, corpus namespacing, job queue and
the rebuilt frontend all in place.

| Metric | Baseline | Now | |
|---|---|---|---|
| Precision@5 | 0.2000 | 0.2000 | unchanged |
| Recall@5 | 0.9623 | 0.9623 | unchanged |
| Hit rate | 0.9623 | 0.9623 | unchanged |
| MRR | 0.8780 | 0.8780 | unchanged |

Retrieval latency is not compared: it is a property of the machine and the
cache state at the time of the run, not of the index. It is now reported as p50
and p95 alongside the mean, because a mean over 53 questions hides the tail.

Reproduce: `GET /evaluation?top_k=5&retriever=dense`.

Three further configurations were re-measured against
[benchmark_report.md](benchmark_report.md), because a single point can match by
luck where a spread cannot:

| Configuration | Report | Re-measured |
|---|---|---|
| hybrid · top-5 | 0.848 MRR / 0.934 recall | 0.8475 / 0.934 |
| sparse · top-5 | 0.715 MRR / 0.811 recall | 0.7154 / 0.811 |
| sparse · top-5 · reranked | 0.888 MRR / 0.924 recall | 0.8884 / 0.924 |

The suite grew rather than shrank — no test was deleted to make a change pass:

| Check | Baseline | Now |
|---|---|---|
| Python tests | 453 | 685 |
| Python coverage | 91% | 94%, and 93.5% without a Groq key (gate: 85%) |
| Frontend unit tests | 224 | 359 (25 files) |
| Frontend E2E tests | — | 5, against a real API and index |
| CI | green | green — lint, Python 3.11, Python 3.12 |

One test was replaced rather than removed: `test_delete_is_not_allowed` asserted
that CORS refused `DELETE`, which was correct when written and became a test
pinning a bug in place once document deletion shipped. It is now derived from
the app's own routes, so the allowlist cannot silently fall behind them again.

82 lines were deleted from `test_chunking.py`, and no assertion went with them:
the file ended with a verbatim copy of `MARKDOWN`, `md_splitter` and
`TestShortChunkMerging`. Python binds the later definition, so the first copy of
the class had been shadowed and never ran. The count is unchanged at 43, which
is what confirms the copies were identical.

## What the suite was not measuring

Three things passed locally for months and were false:

1. **CI had never run the API tests.** `python-multipart` was missing from
   `requirements.txt` for the whole life of the upload endpoint. FastAPI raises
   when it *builds* a route declaring `UploadFile`, so collection aborted and
   every API test errored. It was installed here as another package's
   transitive dependency, which is why only CI saw it.
2. **`GET /settings` was dead without a Groq key.** It declared a `RAGService`
   dependency it never used; building that constructs the Groq client, so the
   endpoint answered 503. Six tests covered it and none of them could fail
   locally, because `GROQ_API_KEY` is set here and unset on the runner.
3. **211 SQLite connections leaked per run.** `DocumentRepository` cached one
   connection per thread and closed none. `pytest` now errors on
   `unclosed database` instead of printing it.

The pattern behind all three: a check that only ever ran in the environment
where it could not fail. `env -u GROQ_API_KEY pytest` is now the pre-push
command for that reason.
