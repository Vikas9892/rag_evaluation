# RAG Evaluation Platform

A Retrieval-Augmented Generation pipeline built from first principles in Python — no
LangChain, no framework abstractions — with a Next.js front end that makes its retrieval
inspectable rather than taking it on trust.

Two modes, over one pipeline:

- **Workspace** — upload your own documents, watch them parse, chunk, embed and index on
  a background worker, then ask questions of them and see the chunks each answer came
  from.
- **Evaluation Lab** — measure whether that retrieval is any good: Precision@K, Recall,
  MRR and hit rate over a labelled dataset, the questions that failed, and a benchmark
  matrix across retrievers, top-K and reranking.

The same retriever answers both, which is what makes the benchmark numbers say anything
about your own documents.

[![CI](https://github.com/Vikas9892/rag_evaluation/actions/workflows/ci.yml/badge.svg)](https://github.com/Vikas9892/rag_evaluation/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/Vikas9892/rag_evaluation/branch/main/graph/badge.svg)](https://codecov.io/gh/Vikas9892/rag_evaluation)

---

## Overview

| Dimension | Choice | Reason |
|-----------|--------|--------|
| Embedding | BAAI/bge-small-en-v1.5 (384-dim) | Best MTEB score under 250 MB |
| Vector index | FAISS IndexFlatIP | Exact cosine search, < 1 ms at 10K vectors |
| Sparse retrieval | BM25Okapi (rank-bm25) | Catches exact-term matches dense models miss |
| Fusion | Reciprocal Rank Fusion (k=60) | State-of-the-art hybrid combining |
| Re-ranking | CrossEncoder ms-marco-MiniLM-L-6 | Fine-grained relevance, 22 M params |
| LLM | Groq / llama-3.1-8b-instant | < 2 s TTFT, free tier for evaluation |
| API | FastAPI + Mangum | Async, auto-OpenAPI docs, Lambda-compatible |
| Deployment | AWS Lambda + HTTP API Gateway | Scale-to-zero, no ops overhead |
| CI | GitHub Actions | Builds the index, then runs the suite on Python 3.11 + 3.12 |

---

## Architecture

```
                      Next.js 16 · React 19 · TanStack Query
  Workspace ─┐                                    ┌─ Evaluation Lab
  upload,    ├──────────► FastAPI ◄───────────────┤  metrics, failures,
  index,     │   SSE stream · REST · OpenAPI      │  benchmark matrix
  query    ──┘                │                   └─
                              │
                    ┌─────────┴─────────┐
                    │                   │
             indexing worker      RAGService.answer()
             (thread or Redis)          │
                    │                   ▼
        parse → chunk → embed      Retriever (below)
                    │
          index/corpora/<id>/  ← one namespace per corpus,
          index/documents.db      evaluation kept separate
```

```
Documents (.pdf .txt .md)
         │
    BaseParser (PyMuPDF / plain-text)
         │
    DocumentSplitter (heading-aware, 250 chars, 50 overlap)
         │
    Embedder (bge-small-en-v1.5, L2-normalised)
         │
  ┌──────┴──────┐
  │             │
vectors.npy  faiss.index          ← offline ingestion
  │             │
  └──────┬──────┘
         │
         ▼
     Retriever
  ┌──────┴──────────┐
  │ FAISS (dense)   │  + BM25 (sparse) → RRF → CrossEncoder (opt-in)
  └──────┬──────────┘
         │ RetrievalResult list
         ▼
    PromptBuilder
         │ Prompt (system + user)
         ▼
    GroqGenerator (llama-3.1-8b-instant)
         │ GenerationResponse
         ▼
    RAGService.answer() → RAGResponse
         │
    FastAPI POST /query → QueryResponse (JSON)
         │
    POST /stream → Server-Sent Events (sources, tokens, done)
         │
    Retrieval trace: per-stage rank and score for every chunk
```

See [docs/benchmark_report.md](docs/benchmark_report.md) for measured retrieval
quality across 18 configurations, [docs/deployment.md](docs/deployment.md) for
shipping it, [docs/architecture.md](docs/architecture.md) for full diagrams,
[docs/product_spec.md](docs/product_spec.md) for the product's central design
decision, and [docs/roadmap.md](docs/roadmap.md) for milestone status and the
open blockers.

---

## Pipeline

### Ingestion (run once)

```bash
# Parse and chunk documents
python scripts/build_embeddings.py

# Build the FAISS index from the stored vectors
python scripts/build_index.py
```

### Evaluation

```bash
# Optional: set GROQ_API_KEY for generation + faithfulness metrics
export GROQ_API_KEY=gsk_...

python scripts/evaluate.py
```

### Ground Truth

Labels are anchored to **content**, not to positional chunk IDs:

```json
{ "id": 13,
  "question": "What are common page replacement algorithms?",
  "expected_answer_spans": ["LRU (Least Recently Used)"] }
```

`ChunkResolver` resolves each span against the live index at evaluation time, and
every span must match **exactly one** chunk — zero matches means the label is
stale, several means it is not discriminative. Both fail the build.

This exists because positional IDs (`os.md_chunk_0001`) are a function of chunk
size, overlap, and separators. Re-chunking silently re-points them at different
text: no error, no test failure, wrong metrics. Changing `CHUNK_SIZE` 500 → 250
once moved MRR from 1.000 to 0.143 that way. A question may carry several spans
when its answer genuinely spans multiple chunks; the relevant set is their union.

### Evaluation Results

Measured over **53 labelled questions** against a **148-chunk corpus**, swept
across 18 configurations (retriever × top-K × reranker).

| Configuration | Precision@5 | Recall@5 | MRR | Hit rate |
|---|---|---|---|---|
| dense · reranked | 0.204 | 0.981 | **0.913** | 0.981 |
| dense | 0.200 | 0.962 | 0.878 | 0.962 |
| hybrid | 0.193 | 0.934 | 0.848 | 0.943 |
| sparse | 0.166 | 0.811 | 0.715 | 0.830 |

Two results worth stating plainly:

- **Dense beats hybrid at every top-K.** RRF gives each retriever an equal vote,
  so fusing with a weaker one drags the ranking below its own better half. The
  default was changed from hybrid to dense because of this.
- **Reranking is the larger lever** — it lifts sparse by 0.173 — but costs
  hundreds of milliseconds against a 300–600 ms generation step, so it stays
  opt-in.

**Precision@K is structurally capped.** With one to two relevant chunks per
question and K retrieved, the ceiling is roughly 1/K. Read Recall and MRR.

Full matrix, method and caveats: [docs/benchmark_report.md](docs/benchmark_report.md).
Regenerate any time with `GET /benchmarks`.

---

## Performance

Measured on a modern laptop CPU (no GPU).  20 iterations each, P95 reported.

| Stage | Mean | P95 | Min |
|-------|------|-----|-----|
| Single embed | 25.7 ms | 40.9 ms | 21.3 ms |
| Batch embed (20 chunks) | 133.2 ms | 153.1 ms | 113.9 ms |
| Per-chunk (batch mode) | **6.7 ms** | 7.7 ms | 5.7 ms |
| FAISS retrieve (top-5) | 27.7 ms | 57.3 ms | 22.1 ms |
| BM25 retrieve (top-5) | **0.2 ms** | 0.3 ms | 0.1 ms |
| Groq LLM generation | ~1–3 s | ~4 s | ~0.5 s |

End-to-end (retrieve + generate): **~1.5–3.5 s**, dominated by the LLM call.

---

## Getting Started

Run the API and the front end together — the browser talks to the API
directly, so both must be up.

```bash
# Terminal 1 — API on :8000
python -m uvicorn api.app:app --port 8000

# Terminal 2 — front end on :3000
cd frontend && npm install && npm run dev
```

The front end reads `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
Only public configuration belongs there: anything in a `NEXT_PUBLIC_` variable
is compiled into the bundle and served to every visitor. The Groq key is read by
the API alone and never reaches the browser.

After changing an API schema, regenerate the client types rather than hand-editing
them — `npm run gen:api` reads the running server's OpenAPI document.

### Prerequisites

- Python 3.11 or 3.12
- `GROQ_API_KEY` (get one free at [console.groq.com](https://console.groq.com))

### Installation

```bash
git clone https://github.com/Vikas9892/rag_evaluation.git
cd rag_evaluation
pip install -r requirements.txt
```

### Docker (recommended)

```bash
# Start the API (requires pre-built index in ./index/)
cp .env.example .env          # add GROQ_API_KEY
docker compose up --build
```

The API is available at `http://localhost:8000`.  Docs at `http://localhost:8000/docs`.

---

## API Reference

### POST /query

Answer a question using the RAG pipeline.

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the Eiffel Tower?", "top_k": 5}'
```

```json
{
  "answer": "The Eiffel Tower is an iron lattice tower on the Champ de Mars in Paris.",
  "sources": [
    {"document_id": "paris_guide", "chunk_id": "paris_guide_chunk_3", "score": 0.9142}
  ],
  "retrieval_latency_ms": 4.2,
  "generation_latency_ms": 1183.0,
  "total_latency_ms": 1187.2,
  "request_id": "3f8a1c20-d42b-4e7e-9b5f-abcdef012345"
}
```

### POST /stream

Stream answer tokens via Server-Sent Events.

```bash
curl -N -X POST http://localhost:8000/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain RAG"}'
```

```
data: {"type": "sources", "data": [...]}
data: {"type": "token", "data": "RAG"}
data: {"type": "token", "data": " stands"}
...
data: {"type": "done"}
```

### GET /health

```bash
curl http://localhost:8000/health
# {"status": "healthy"}
```

### GET /metrics

```bash
curl http://localhost:8000/metrics
# {"total_queries": 42, "avg_retrieval_ms": 24.1, "avg_generation_ms": 1820.3, "errors": 0}
```

### Documents and corpora

Uploads are asynchronous. `POST /documents` returns `202` with a job id and the
document in `QUEUED`; the worker moves it through parsing, chunking, embedding and
indexing, and the client polls until it reports `READY` or `FAILED`.

```bash
# Upload into a named corpus. 25 MB limit; .pdf .txt .md .markdown.
curl -X POST "http://localhost:8000/documents?corpus_id=workspace"      -F "file=@notes.md"
# {"document_id": "8e275e…", "job_id": "…", "status": "QUEUED"}

curl "http://localhost:8000/documents/8e275e…/status"
# {"status": "EMBEDDING", "progress": 0.66, "chunk_count": 0, "error": null}

# Removing a document rebuilds the index from the vectors already on disk —
# nothing is re-embedded.
curl -X DELETE "http://localhost:8000/documents/8e275e…"
# {"deleted": true, "chunks_removed": 6, "chunks_remaining": 142}

curl http://localhost:8000/corpora
# {"corpora": [{"corpus_id": "evaluation", "chunks": 148, "is_evaluation": true}, …]}

# Whether indexing is durable. The in-process worker recovers unfinished jobs
# on restart but loses queued ones; set REDIS_URL for a shared, durable queue.
curl http://localhost:8000/queue
```

A byte-identical file already in the corpus returns the existing document and
queues nothing. Corpus ids must match `^[a-z0-9][a-z0-9_-]{0,63}$` — a bad id is
refused rather than sanitised, since the id becomes a directory name.

Every query endpoint takes an optional `corpus_id`; omitted, it means the
benchmark corpus, which uploads never touch.

---

## Testing

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=. --cov-report=term-missing

# Phase-specific
pytest tests/test_api.py -v
pytest tests/test_hybrid_retriever.py -v
```

**685 tests, 94% coverage**, gated at 85% in CI. The uncovered lines are
real-API paths (`GroqGenerator`) that need a live key.

> **Run it once the way CI does, before pushing.**
>
> ```bash
> env -u GROQ_API_KEY pytest --cov=. --cov-fail-under=85
> ```
>
> The runner has no `GROQ_API_KEY`, so a suite that is green locally can still
> fail there. That is not hypothetical: `GET /settings` declared a `RAGService`
> dependency it never used, which constructs the Groq client, so the endpoint
> answered 503 on any deployment without a key. Six tests caught it — none of
> which could run locally, because the key was set. Coverage without the key is
> ~93.7%, still above the gate.

`pytest` fails on an unclosed SQLite connection rather than warning about it.
The document repository keeps one connection per thread; leaving them open is a
leak, and on Windows it holds the database file against the `tmp_path` teardown
that follows.

### Linting

```bash
ruff check .          # pyflakes + pycodestyle errors
black --check .       # formatting
```

Both run as their own CI job, without the index build — waiting for model
weights to report an unused import would discourage running them at all. Ruff
is limited to `E` and `F`: this codebase predates having a linter, and the full
default rule set would bury an undefined name under style noise. `E501` is off
because line length is black's decision.

### Frontend

```bash
cd frontend
npm run verify        # typecheck, lint, format check, then the unit suite
npm run test:e2e      # Playwright — needs both servers already running
```

`verify` mocks the API, which is right for asserting what the UI does with a
response and useless for asserting that the API is reachable at all. The
end-to-end suite covers that seam against a real index: an upload reaching the
worker, a question answered from the uploaded corpus rather than the benchmark
one, and a deleted document leaving the index as well as the list. It found a
CORS misconfiguration that had broken document deletion in every browser while
every unit test passed.

It is deliberately not part of `verify`: it needs two servers and a browser, and
a check that cannot be run casually is one that stops being run.

---

## Deployment

### AWS Lambda (SAM)

```bash
# Store your Groq key in SSM first
aws ssm put-parameter \
  --name /rag/groq_api_key \
  --value "gsk_..." \
  --type SecureString

# Build and deploy
sam build
sam deploy --guided
```

See [aws/template.yaml](aws/template.yaml) for the full SAM template.

### Local (uvicorn)

```bash
export GROQ_API_KEY=gsk_...
uvicorn api.app:app --reload
```

### Load Testing

```bash
locust -f load_tests/locustfile.py \
       --host http://localhost:8000 \
       --headless -u 10 -r 2 -t 60s
```

---

## Project Structure

```
rag_evaluation/
├── config/               # Settings and logging
├── ingestion/            # BaseParser, PyMuPDF, plain-text loaders
├── chunking/             # Chunk dataclass, RecursiveChar splitter
├── embeddings/           # Embedder (bge-small), VectorStorage (incremental)
├── retrieval/
│   ├── faiss_store.py    # FAISS IndexFlatIP wrapper
│   ├── bm25_store.py     # BM25Okapi sparse retrieval
│   ├── hybrid_retriever.py  # RRF fusion
│   ├── reranker.py       # CrossEncoder re-ranking
│   └── retriever.py      # Dense retriever (embed + FAISS search)
├── generation/           # PromptBuilder, GroqGenerator (streaming)
├── services/             # RAGService (answer + stream)
├── api/
│   ├── schemas.py        # Pydantic request/response models
│   ├── dependencies.py   # lru_cache singleton injection
│   └── routers/          # /query /stream /health /metrics
├── aws/                  # Mangum handler, SAM template
├── corpora/              # Per-corpus paths, id validation, index rebuild
├── documents/            # Document records (SQLite), upload storage
├── jobs/                 # Job queue (in-process / Redis), indexing worker
├── evaluation/           # Metrics, BenchmarkRunner, ReportGenerator
├── scripts/              # Ingestion, evaluation, benchmark CLI scripts
├── tests/                # unit, contract and API tests; 85% coverage gate
├── load_tests/           # Locust load test scenarios
├── frontend/
│   ├── app/              # Next.js routes: overview, workspace, query,
│   │                     #   evaluation, benchmarks, settings, about
│   ├── components/       # UI, one folder per surface
│   ├── hooks/            # TanStack Query hooks
│   ├── lib/              # URL params, sorting and recommendation logic
│   ├── services/api.ts   # The only place that talks to the API
│   ├── types/            # Generated from the live OpenAPI schema
│   └── e2e/              # Playwright, against a real API and index
├── docs/
│   ├── architecture.md   # System diagrams
│   └── decisions/        # 8 Architecture Decision Records
├── Dockerfile            # Multi-stage production image
├── docker-compose.yml    # One-command local deployment
└── .github/workflows/ci.yml  # GitHub Actions (Python 3.11 + 3.12)
```

---

## Design Decisions

Eight Architecture Decision Records document the key technical choices:

| # | Decision | Summary |
|---|----------|---------|
| [001](docs/decisions/001-parser.md) | Document Parser | BaseParser + registry; PyMuPDF over pypdf |
| [002](docs/decisions/002-recursive-chunking.md) | Chunking | Heading-aware 250/50 with a merge floor; why not sentence splitters |
| [003](docs/decisions/003-bge.md) | Embedding Model | BGE-small: best MTEB/MB ratio under Lambda limit |
| [004](docs/decisions/004-faiss.md) | Vector Index | IndexFlatIP exact search; why not HNSW at this scale |
| [005](docs/decisions/005-provider-abstraction.md) | Abstractions | BaseGenerator/Parser/Reranker; testability rationale |
| [006](docs/decisions/006-evaluation.md) | Evaluation | Separate retrieval vs generation metrics; LLM-as-judge |
| [007](docs/decisions/007-lambda.md) | Deployment | Lambda vs Fargate; Mangum; HTTP API vs REST API |
| [008](docs/decisions/008-frontend-architecture.md) | Frontend | Next.js App Router; types generated from OpenAPI; TanStack Query |

---

## Limitations

Stated because a platform that measures other systems' retrieval should be
straight about its own.

- **Indexing durability.** The default worker is a thread in the API process. It
  recovers documents left mid-pipeline by a restart, but a job still queued when
  the process dies is lost, and each process consumes its own queue. `GET /queue`
  reports this rather than implying otherwise, and the Workspace says so on the
  page. Setting `REDIS_URL` switches to a durable shared queue; that path is
  tested against a stub client, not a live server.
- **Dataset size.** 53 labelled questions over 148 chunks. Differences of a few
  hundredths of MRR are within the noise of one question changing rank, which is
  why the benchmark page reports a tolerance band instead of crowning a winner.
- **Precision@K is structurally capped** near 1/K on this dataset. It is reported
  because omitting an inconvenient metric is worse, but Recall and MRR are the
  ones to read.
- **Deleting rebuilds the whole index** for that corpus. It is exact and does not
  re-embed, but it is O(corpus) per deletion and would need a tombstone-and-compact
  scheme at a size where that matters.
- **Latency figures are machine-dependent.** They are measured on the host that
  served the request, and reported as p50 and p95 rather than a mean so the tail
  is visible.
- **No authentication.** Every corpus is visible to every caller. This is a
  single-tenant tool; multi-tenancy would need auth before uploads could be
  considered private.

---

## Future Work

### Short-term
- **Streaming LLM tokens to the browser** via WebSocket (instead of SSE)
- **Caching** frequent queries with Redis to avoid redundant LLM calls
- **Query rewriting** — rephrase the user question before retrieval

### Medium-term
- **Multi-vector retrieval (ColBERT)** — per-token embeddings for finer-grained matching
- **Contextual chunk compression** — summarise retrieved passages to fit more context
- **Feedback loop** — record user ratings and use them to re-train the embedding model

### Production hardening
- Store FAISS index and model weights in S3; load into `/tmp` at Lambda cold start
- Lambda SnapStart (when available for Python) to eliminate cold starts
- OpenTelemetry instrumentation for distributed tracing
