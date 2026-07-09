# RAG Evaluation System

A production-grade Retrieval-Augmented Generation pipeline built from first principles
in Python — no LangChain magic, no framework abstractions.  Every component is tested,
benchmarked, and deployable to AWS Lambda in one command.

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
| CI | GitHub Actions | Every PR runs 289 tests across Python 3.11 + 3.12 |

---

## Architecture

```
Documents (.pdf .txt .md)
         │
    BaseParser (PyMuPDF / plain-text)
         │
    DocumentSplitter (RecursiveChar, 500 chars, 100 overlap)
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
  │ FAISS (dense)   │  + BM25 (sparse) → RRF → CrossEncoder (optional)
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
```

See [docs/architecture.md](docs/architecture.md) for full diagrams.

---

## Pipeline

### Ingestion (run once)

```bash
# Parse and chunk documents
python scripts/chunk_documents.py

# Embed chunks and build FAISS index
python scripts/embed_chunks.py
```

### Evaluation

```bash
# Optional: set GROQ_API_KEY for generation + faithfulness metrics
export GROQ_API_KEY=gsk_...

python scripts/evaluate.py
```

### Evaluation Results

Measured on a 15-question ground-truth dataset built from the indexed documents.

| Metric | Score |
|--------|-------|
| Precision@5 | 0.20 |
| Recall@5 | 1.00 |
| Hit Rate | 1.00 |
| MRR | 1.00 |
| Semantic Similarity | 0.47 |

- **MRR = 1.0** — the relevant chunk is always ranked first.
- **Recall = 1.0** — every relevant chunk is retrieved within the top-5.
- **Precision@5 = 0.20** is expected: there is exactly 1 relevant chunk per question
  and 5 are retrieved (1/5 = 0.20).

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

**Coverage: 87%** across 289 tests.  The uncovered lines are real-API paths
(GroqGenerator, RAGService.answer) that require a live GROQ_API_KEY.

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
├── evaluation/           # Metrics, BenchmarkRunner, ReportGenerator
├── scripts/              # Ingestion, evaluation, benchmark CLI scripts
├── tests/                # 289 tests, 87% coverage
├── load_tests/           # Locust load test scenarios
├── docs/
│   ├── architecture.md   # System diagrams
│   └── decisions/        # 7 Architecture Decision Records
├── Dockerfile            # Multi-stage production image
├── docker-compose.yml    # One-command local deployment
└── .github/workflows/ci.yml  # GitHub Actions (Python 3.11 + 3.12)
```

---

## Design Decisions

Seven Architecture Decision Records document the key technical choices:

| # | Decision | Summary |
|---|----------|---------|
| [001](docs/decisions/001-parser.md) | Document Parser | BaseParser + registry; PyMuPDF over pypdf |
| [002](docs/decisions/002-recursive-chunking.md) | Chunking | RecursiveChar 500/100; why not sentence splitters |
| [003](docs/decisions/003-bge.md) | Embedding Model | BGE-small: best MTEB/MB ratio under Lambda limit |
| [004](docs/decisions/004-faiss.md) | Vector Index | IndexFlatIP exact search; why not HNSW at this scale |
| [005](docs/decisions/005-provider-abstraction.md) | Abstractions | BaseGenerator/Parser/Reranker; testability rationale |
| [006](docs/decisions/006-evaluation.md) | Evaluation | Separate retrieval vs generation metrics; LLM-as-judge |
| [007](docs/decisions/007-lambda.md) | Deployment | Lambda vs Fargate; Mangum; HTTP API vs REST API |

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
