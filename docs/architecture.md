# System Architecture

## Overview

The RAG Evaluation System is a production-grade Retrieval-Augmented Generation pipeline
built in Python.  Documents are ingested offline; at query time the system retrieves
relevant passages and feeds them as grounded context to an LLM.

---

## Query-time Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ POST /query  (JSON)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (HTTP API)                        │
│                   AWS SAM / CloudFormation                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ Mangum ASGI adapter
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
         │  chunk_size=500, overlap=100
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

## AWS Deployment

```
┌─────────────────────────────────────────────────────┐
│                     AWS Region                       │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │              API Gateway (HTTP API)           │   │
│  └────────────────────┬─────────────────────────┘   │
│                       │                             │
│  ┌────────────────────▼─────────────────────────┐   │
│  │              Lambda Function                  │   │
│  │  handler = Mangum(FastAPI app)                │   │
│  │  Runtime: Python 3.12 · Memory: 1024 MB       │   │
│  │  Timeout: 60 s                                │   │
│  └──────────┬────────────────────────────────────┘   │
│             │                                       │
│     ┌───────▼────────┐  ┌──────────────────────┐   │
│     │  Parameter     │  │  CloudWatch Logs      │   │
│     │  Store (SSM)   │  │  (JSON structured)    │   │
│     │  GROQ_API_KEY  │  │                       │   │
│     └────────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## Module Dependency Graph

```
config/
  └── settings.py, logging_config.py

ingestion/
  └── parser.py → loader.py → document.py → cleaner.py

chunking/
  └── chunk.py ← splitter.py

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
  └── lambda_handler.py     (Mangum wrapper)
  └── template.yaml         (SAM/CloudFormation)

evaluation/
  └── metrics.py (pure functions)
  └── dataset.py
  └── retrieval_evaluator.py
  └── generation_evaluator.py
  └── benchmark.py
  └── report.py
```
