# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-07-10

### Phase 8 — Production Grade

#### Added
- **GitHub Actions CI** — tests run on Python 3.11 and 3.12 on every push/PR;
  HuggingFace model cache is persisted across runs; coverage uploaded to Codecov
- **Docker** — multi-stage `Dockerfile` (builder → runtime); `docker-compose.yml`
  for one-command local deployment with bind-mounted index volume
- **OpenAPI documentation** — endpoint summaries, descriptions, request/response
  examples, and explicit error response codes in all FastAPI routers
- **Architecture documentation** — `docs/architecture.md` with ASCII diagrams for
  query-time, ingestion, hybrid retrieval, and AWS deployment flows
- **Architecture Decision Records** — seven ADRs in `docs/decisions/` covering
  parser choice, chunking strategy, embedding model, FAISS, provider abstractions,
  evaluation design, and Lambda deployment rationale
- **Hybrid retrieval (BM25 + FAISS)** — `retrieval/bm25_store.py` (BM25Okapi) and
  `retrieval/hybrid_retriever.py` (Reciprocal Rank Fusion, k=60)
- **Cross-encoder re-ranking** — `retrieval/reranker.py` (`BaseReranker` ABC +
  `CrossEncoderReranker` using ms-marco-MiniLM-L-6-v2)
- **Streaming responses** — `BaseGenerator.stream()` interface; `GroqGenerator.stream()`
  implementation; `POST /stream` SSE endpoint; `RAGService.stream()` yields typed events
- **Incremental index updates** — `VectorStorage.append()` adds new chunks without
  rebuilding the full index
- **Performance benchmarking** — `scripts/benchmark_performance.py` measures per-stage
  latency (embed, retrieve, BM25); outputs `reports/benchmark.json`
- **Load testing** — `load_tests/locustfile.py` simulates concurrent users hitting
  `/query`, `/health`, and `/metrics`
- **`pyproject.toml`** — unified pytest and coverage configuration
- **README 2.0** — overview table, architecture diagram, evaluation results, real
  performance numbers, API examples, deployment guide, project structure, ADR index

#### Changed
- `api/schemas.py` — added Pydantic `json_schema_extra` examples on all models
- `api/routers/health.py`, `query.py` — added `summary`, `description`, `responses`
  metadata for OpenAPI
- `api/app.py` — added `openapi_tags`, streaming router, richer description
- `retrieval/__init__.py` — exports `BM25Store`, `HybridRetriever`, `BaseReranker`,
  `CrossEncoderReranker`
- `generation/generator.py` — added `BaseGenerator.stream()` (raises
  `NotImplementedError` by default) and `GroqGenerator.stream()` implementation
- `services/rag_service.py` — added `RAGService.stream()` that yields SSE event dicts
- `requirements.txt` — added `rank-bm25>=0.2.2`, `locust>=2.20.0`

#### Tests
- `tests/test_bm25_store.py` — 13 tests for BM25Store (init, search, edge cases)
- `tests/test_hybrid_retriever.py` — 8 tests for RRF fusion correctness
- `tests/test_reranker.py` — 7 tests for CrossEncoderReranker (mocked model)
- `tests/test_stream.py` — 11 tests for SSE streaming endpoint
- `tests/test_incremental.py` — 9 tests for VectorStorage.append + FAISSStore.add

**Total: 289 tests | Coverage: 87%**

---

## [0.7.0] — 2026-07-09

### Phase 7 — Production API & AWS Deployment

#### Added
- `services/rag_service.py` — `RAGService` orchestrates retrieval + generation,
  tracks in-process metrics (queries, latencies, errors)
- `api/schemas.py` — Pydantic v2 `QueryRequest` / `QueryResponse` / `SourceInfo`
- `api/dependencies.py` — `lru_cache` singleton loader; 503 on missing index / key
- `api/routers/health.py` — `GET /health`, `GET /metrics`
- `api/routers/query.py` — `POST /query` with 400/500/503/504 error mapping
- `api/app.py` — `create_app()` factory + module-level `app`
- `aws/lambda_handler.py` — Mangum ASGI adapter (`lifespan="off"`)
- `aws/template.yaml` — SAM template; HTTP API Gateway; SSM-backed `GROQ_API_KEY`
- `tests/test_api.py` — 29 tests covering success, validation, and error paths

**Total: 240 tests**

---

## [0.6.0] — 2026-07-09

### Phase 6 — Evaluation Pipeline

#### Added
- `evaluation/metrics.py` — pure functions: Precision@K, Recall@K, Hit Rate, MRR,
  cosine similarity, MRR
- `evaluation/dataset.py` — `BenchmarkSample`, `DatasetLoader`
- `evaluation/retrieval_evaluator.py` — per-sample and aggregate retrieval metrics
- `evaluation/generation_evaluator.py` — semantic similarity, LLM-as-judge faithfulness
- `evaluation/benchmark.py` — `BenchmarkRunner`, `ExperimentRunner`
- `evaluation/report.py` — CSV (per-question) and Markdown summary reports
- `evaluation/dataset.json` — 15-question ground-truth dataset
- `scripts/evaluate.py` — CLI script; degrades gracefully without `GROQ_API_KEY`

---

## [0.5.0] — 2026-07-08

### Phase 5 — Generation Pipeline

#### Added
- `generation/models.py` — `Prompt`, `GenerationResponse` dataclasses
- `generation/prompt_builder.py` — `PromptBuilder`; `[Source N]` context format
- `generation/generator.py` — `BaseGenerator` ABC; `GroqGenerator` with exponential
  backoff retries on rate-limit and timeout errors

---

## [0.4.0] — 2026-07-07

### Phase 4 — FAISS Retrieval

#### Added
- `retrieval/faiss_store.py` — `FAISSStore` (IndexFlatIP, L2-normalised)
- `retrieval/ranking.py` — `RetrievalResult` dataclass
- `retrieval/retriever.py` — `Retriever.from_disk()` factory

---

## [0.3.0] — 2026-07-06

### Phase 3 — Embeddings

#### Added
- `embeddings/embedder.py` — `Embedder` (bge-small-en-v1.5, batch inference)
- `embeddings/service.py` — `EmbeddingService`
- `embeddings/storage.py` — `VectorStorage` (vectors.npy + metadata.json)

---

## [0.2.0] — 2026-07-05

### Phase 2 — Chunking Pipeline

#### Added
- `chunking/chunk.py` — `Chunk` dataclass
- `chunking/splitter.py` — `DocumentSplitter` (RecursiveCharacterTextSplitter)

---

## [0.1.0] — 2026-07-04

### Phase 1 — Document Ingestion

#### Added
- `ingestion/document.py` — `Document` dataclass
- `ingestion/parser.py` — `BaseParser` ABC, `PyMuPDFParser`, `PlainTextParser`
- `ingestion/loader.py` — `DocumentLoader` with extension-keyed registry
- `ingestion/cleaner.py` — `DocumentCleaner`
- `config/settings.py` — central configuration
- `config/logging_config.py` — rotating file + console logger
