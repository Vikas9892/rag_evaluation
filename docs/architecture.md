# System Architecture

## Overview

The RAG Evaluation Platform is a Retrieval-Augmented Generation pipeline built in
Python, with a Next.js front end. At query time the system retrieves relevant passages
and feeds them as grounded context to an LLM.

Documents reach the index two ways. The benchmark corpus is built offline by scripts, so
its contents — and therefore every published metric — are reproducible from the
repository. A user's own documents are uploaded through the API and indexed
asynchronously. Both land in the same shape and are read by the same retriever; only
the namespace differs.

---

## Corpus namespacing

One index per corpus, resolved through `corpora/layout.py`:

```
index/
├── faiss.index          ┐
├── metadata.json        ├─ the evaluation corpus keeps its original paths,
├── vectors.npy          ┘  so every published number stays reproducible
├── corpora/
│   └── <corpus_id>/     ← everything uploaded, one directory per corpus
│       ├── faiss.index
│       ├── metadata.json
│       └── vectors.npy
├── uploads/<corpus_id>/ ← stored files, named by document id
└── documents.db         ← SQLite: per-document status and lifecycle
```

A corpus id must match `^[a-z0-9][a-z0-9_-]{0,63}$`. Invalid ids raise rather than being
sanitised: the id becomes a directory name, so quietly rewriting `../../etc` hides an
attack where refusing it surfaces one. The frontend mirrors the same pattern, and a
contract test fails if the two ever disagree.

`RAGService` instances are cached per corpus, and the cache is invalidated when a
document is indexed or deleted — otherwise a query would be answered from an index that
no longer exists on disk.

---

## Asynchronous indexing

```
POST /documents  ──►  validate (size, type, filename)
                      store file under index/uploads/<corpus>/
                      insert record: status = QUEUED
                      enqueue job                     ──► 202 + job id
                                                           │
   JobQueue (InProcessQueue thread, or RedisQueue)  ◄───────┘
                      │
   DocumentIndexer    ▼
      parse ─► clean ─► chunk ─► embed ─► index
        │       │        │        │        │
        └───────┴────────┴────────┴────────┴─► status written at each stage
                                                (PARSING … INDEXING … READY)
```

The client polls `GET /documents/{id}/status` and stops when the status is terminal.
Chunks are appended through `VectorStorage.append()` rather than triggering a rebuild.

Durability is reported, not implied. `InProcessQueue` runs a worker thread inside the
API process: on startup, documents left mid-pipeline by a restart are requeued, but a
job still sitting in the queue when the process died is gone. `GET /queue` says which
backend is in use and whether it is durable, and the Workspace surfaces that. Setting
`REDIS_URL` switches to a shared queue that survives a restart.

Deletion filters the corpus's metadata and vectors by `document_id` and rebuilds the
FAISS index from the vectors already on disk — exact, and without re-embedding
anything. It is O(corpus) per deletion, which is the right trade at this scale and
would need tombstones at a larger one.

---

## Query-time Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ POST /query  (JSON)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Caddy  (TLS, Let's Encrypt)                     │
│                  reverse_proxy → api:8000                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP, inside the Docker network
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FastAPI App                                │
│    ┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│    │ POST /query  │  │  POST /stream   │  │   GET /health   │  │
│    └──────┬───────┘  └────────┬────────┘  └─────────────────┘  │
│           │  Depends(get_service)          GET /metrics          │
└───────────┼──────────────────┼────────────────────────────────┘
            │                  │
            ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│                        RAGService                             │
│   answer(question, top_k) → RAGResponse                       │
│   stream(question, top_k) → Generator[dict]                   │
└──────────────────────────┬───────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    ┌──────────┐   ┌──────────────┐  ┌──────────────┐
    │ Retriever│   │PromptBuilder │  │BaseGenerator │
    │ (FAISS)  │   │              │  │(GroqGenerator│
    └──────────┘   └──────────────┘  │ / streaming) │
                                     └──────────────┘
```

---

## Ingestion Pipeline (offline)

```
┌─────────────────┐
│  Raw Documents  │
│  (.pdf .txt .md)│
└────────┬────────┘
         │  BaseParser  (PyMuPDF / plain-text)
         ▼
┌─────────────────┐
│  Document list  │
│  (title, text)  │
└────────┬────────┘
         │  DocumentSplitter  (RecursiveCharacterTextSplitter)
         │  chunk_size=250, overlap=50
         │  separators: "\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""
         │  then merge chunks shorter than MIN_CHUNK_CHARS=50
         ▼
┌─────────────────┐
│  Chunk list     │
│  (text, offsets)│
└────────┬────────┘
         │  Embedder  (BAAI/bge-small-en-v1.5)
         │  L2-normalised float32 vectors, dim=384
         ▼
┌─────────────────┐
│  vectors.npy    │  ← index/vectors.npy
│  metadata.json  │  ← index/metadata.json
└────────┬────────┘
         │  FAISSStore.add()
         ▼
┌─────────────────┐
│  faiss.index    │  ← index/faiss.index
│  (IndexFlatIP)  │
└─────────────────┘
```

---

## Hybrid Retrieval Architecture

```
                        Query
                          │
           ┌──────────────┴──────────────┐
           ▼                             ▼
    ┌──────────────┐             ┌──────────────┐
    │  Dense FAISS │             │  Sparse BM25 │
    │  (semantic)  │             │  (keyword)   │
    │  top-20 hits │             │  top-20 hits │
    └──────┬───────┘             └──────┬───────┘
           │                           │
           └──────────────┬────────────┘
                          ▼
               ┌─────────────────────┐
               │  Reciprocal Rank    │
               │  Fusion  (k=60)     │
               │  score = Σ 1/(k+r)  │
               └──────────┬──────────┘
                          ▼
                     Top-K Results
```

---

## Cross-Encoder Re-ranking

```
Query + Top-K*M candidates (e.g. 20)
           │
           ▼
┌────────────────────────────────┐
│ CrossEncoder.predict(pairs)    │
│ ms-marco-MiniLM-L-6-v2         │
│ reads query+passage jointly    │
└──────────────┬─────────────────┘
               │ fine-grained relevance scores
               ▼
          Sorted top-K
```

---

## AWS Deployment — what actually runs

The API is one EC2 instance running two containers. There is no API Gateway, no
Lambda and no SSM in the live path; `aws/template.yaml` is retained but not
deployed — see [deployment.md](deployment.md) for the three reasons it does not
fit this workload.

```
        Browser
           │ HTTPS
           ▼
┌──────────────────────┐        ┌─────────────────────────────────────────┐
│  Vercel (front end)  │        │        AWS ap-south-1                    │
│  Next.js, static +   │        │                                          │
│  CDN, root: frontend │        │  EC2 t4g.small — 2 vCPU Graviton, 2 GiB  │
└──────────┬───────────┘        │  ┌────────────────────────────────────┐  │
           │                    │  │ caddy:2-alpine   :80 :443          │  │
           │  the browser calls │  │ Let's Encrypt, auto-renewed        │  │
           │  the API directly  │  └──────────────┬─────────────────────┘  │
           └───────────────────────────────────►  │ reverse_proxy          │
              HTTPS, CORS-checked│  ┌─────────────▼─────────────────────┐  │
                                 │  │ rag-api  (uvicorn :8000)          │  │
                                 │  │ corpus + model weights baked into │  │
                                 │  │ the image at build time           │  │
                                 │  │ .env (chmod 600) → GROQ_API_KEY   │  │
                                 │  └─────────────┬─────────────────────┘  │
                                 │                │                        │
                                 │      ┌─────────▼──────────┐             │
                                 │      │ EBS gp3, named vol │             │
                                 │      │ /app/index         │             │
                                 │      │ uploads + SQLite   │             │
                                 │      │ survive a restart  │             │
                                 │      └────────────────────┘             │
                                 └─────────────────────────────────────────┘
```

**Why an instance and not a function.** The API holds 743 MB resident with the
model and index loaded, needs a writable filesystem for uploads and the document
database, and runs a background worker that must outlive a request. A function
gives none of those. DuckDNS supplies the hostname the certificate is issued for.

---

## Module Dependency Graph

```
config/
  └── settings.py, logging_config.py

ingestion/
  └── parser.py → loader.py → document.py → cleaner.py

chunking/
  └── chunk.py ← splitter.py   (heading-aware split, then short-chunk merge)

embeddings/
  └── embedder.py → service.py → storage.py

retrieval/
  └── faiss_store.py
  └── bm25_store.py
  └── hybrid_retriever.py  (uses Retriever + BM25Store)
  └── reranker.py
  └── ranking.py
  └── retriever.py          (uses FAISSStore + Embedder)

generation/
  └── models.py ← prompt_builder.py ← generator.py

services/
  └── rag_service.py        (uses Retriever + PromptBuilder + BaseGenerator)

api/
  └── schemas.py
  └── dependencies.py       (uses RAGService, lru_cache)
  └── routers/
      └── health.py
      └── query.py
      └── stream.py
  └── app.py

aws/
  └── lambda_handler.py     (Mangum wrapper — retained, not deployed)
  └── template.yaml         (SAM/CloudFormation)

evaluation/
  └── metrics.py (pure functions)
  └── ground_truth.py       (ChunkResolver: content span -> chunk_id)
  └── dataset.py            (DatasetLoader, resolver injected)
  └── retrieval_evaluator.py
  └── generation_evaluator.py
  └── benchmark.py
  └── report.py
```

### Ground-truth resolution

Labels are authored as content spans and bound to chunk IDs at evaluation time,
so re-chunking cannot silently invalidate them.

```
dataset.json                index/metadata.json
"expected_answer_spans"           │
        │                         │
        └──────► ChunkResolver ◄──┘
                      │
              exactly 1 match?
                 │        │
               yes        no ──► GroundTruthError  (stale or ambiguous label)
                 │
                 ▼
        BenchmarkSample.expected_chunk_ids
                 │
                 ▼
          RetrievalEvaluator ──► Precision@K · Recall · MRR · Hit Rate
```

`DatasetLoader` takes the resolver as a constructor-style argument rather than
building one itself: unit tests inject an in-memory resolver (or use the legacy
literal-ID form) and never need an index on disk, while `scripts/evaluate.py`
injects `ChunkResolver.from_disk()` and fails loudly on any stale label.
