# RAG Evaluation Platform — Product Specification

**Status:** Draft · Milestone 1
**Owner:** Vikas9892
**Last updated:** 2026-08-11

---

## 1. Product Vision

An engineering platform to **build, evaluate, benchmark, and visualise** Retrieval-Augmented
Generation systems.

This is deliberately *not* a chatbot. A chatbot answers questions; this platform answers a
harder question: **"is the retrieval actually any good, and how do you know?"**

The product treats a RAG pipeline as a system under measurement. Every stage — chunking,
embedding, dense search, sparse search, fusion, reranking, generation — is observable,
configurable, and comparable against a labelled dataset.

### Positioning

| | Chatbot demo | This platform |
|---|---|---|
| Primary output | an answer | evidence about answer quality |
| Retrieval | hidden | fully traced, per-stage |
| Config changes | invisible | benchmarked side-by-side |
| "Is it better?" | vibes | Precision@K / Recall / MRR on labelled data |

---

## 2. The Central Design Decision: Observability vs. Accuracy

**Accuracy metrics require ground truth. Ad-hoc questions have none.**

`precision_at_k(retrieved_ids, relevant_ids, k)` needs `relevant_ids` — the human-labelled
set of chunks that *should* have been retrieved. For a question a user typed two seconds ago,
that set does not exist and cannot be inferred. Any Precision@5 rendered next to an ad-hoc
answer would be fabricated.

The product therefore splits into two surfaces that must never be conflated:

### Surface A — Query (ad-hoc, unlabelled)

Shows only what is **directly observable** from a single request:

- generated answer
- retrieved chunks with per-stage scores and ranks
- stage-by-stage latency
- token usage and cost
- retriever agreement (did dense and sparse pick the same chunks?)

**Never shows** Precision, Recall, MRR, or any accuracy metric.

### Surface B — Evaluation (dataset, labelled)

Runs the pipeline across the labelled dataset and reports **computable accuracy**:

- Precision@K, Recall@K, Hit Rate, MRR
- semantic similarity, faithfulness (LLM-judge)
- aggregate latency and token cost

Refreshed per benchmark run, not per request.

### Honest proxies allowed on Surface A

Signals that *correlate* with quality without needing labels, clearly framed as heuristics:

- **score margin** — gap between rank-1 and rank-2 (low margin ⇒ ambiguous retrieval)
- **retriever agreement** — overlap between dense and sparse top-K
- **grounding** — did the LLM abstain ("I don't know")? An abstention is a *correct*
  outcome when the corpus lacks the answer, and must be surfaced as such, not as failure.

---

## 3. Ground Truth Integrity (blocking constraint)

The current dataset anchors labels to **positional** chunk IDs:

```json
{ "id": 13, "expected_chunk_ids": ["os.md_chunk_0001"] }
```

Positional IDs are a function of chunk size, overlap, and separators. Any chunking change
silently re-points every label at different content. Observed on 2026-08-11: changing
`CHUNK_SIZE` 500→250 moved MRR from 1.000 to 0.143 with **no error raised** — the IDs still
resolved, they just meant something else.

This is an evaluation-integrity failure, and it is precisely the class of bug this platform
exists to detect. It cannot be tolerated in the product's own foundation.

**Required design:** labels anchor to **content**, resolved to chunk IDs at evaluation time.

```json
{ "id": 13,
  "question": "What are common page replacement algorithms?",
  "expected_answer_span": "FIFO\n- LRU (Least Recently Used)\n- Optimal" }
```

**Required invariant, enforced in CI:** every `expected_answer_span` must resolve to exactly
one chunk in the current index. Zero matches or multiple matches fails the build.

Benchmarks that vary chunk size are only meaningful once this holds — otherwise the platform
is comparing configurations against labels that mean different things in each configuration.

---

## 4. User Journeys

### J1 — "Is my retrieval broken for this question?"
Query page → type question → read answer → expand retrieval trace → see that dense ranked the
wrong chunk first and sparse corrected it → conclude the embedding is weak on literal phrases.

### J2 — "Did my change help?"
Change chunk size → rebuild index → Evaluation page → run benchmark → compare against previous
run → see Recall@5 up, latency flat → keep the change.

### J3 — "Which configuration should ship?"
Benchmarks page → matrix of {chunk size} × {top-K} × {retriever} → sort by MRR → inspect the
latency cost of the winner → choose the knee of the curve.

### J4 — "Why did it say 'I don't know'?"
Query page → abstention badge → retrieval trace shows top score below threshold → conclude the
corpus genuinely lacks the answer → add the source document.

---

## 5. Pages

| Route | Purpose | Primary data source |
|---|---|---|
| `/` | Overview: system health, corpus size, last benchmark summary | `GET /health`, `GET /metrics` |
| `/query` | Ad-hoc question, answer, retrieval trace, pipeline viz | `POST /query`, `POST /stream` |
| `/evaluation` | Metrics over the labelled dataset | `POST /evaluate`, `GET /evaluations` |
| `/benchmarks` | Configuration comparison matrix and charts | `GET /benchmarks` |
| `/settings` | Runtime knobs: top-K, retriever, reranker toggle | client state + `GET /config` |
| `/about` | Architecture, trade-offs, methodology | static |

---

## 6. API Contracts

### 6.1 Retrieval trace (new — required by the UI)

The current `SourceInfo` exposes a single fused `score`. The retrieval table requires
per-stage attribution, so `HybridRetriever` must stop discarding component ranks.

```ts
interface RetrievedChunk {
  chunk_id: string
  document_id: string
  text: string
  rank: number                 // final rank after all stages
  scores: {
    dense:    { score: number; rank: number } | null   // null = stage not run
    sparse:   { score: number; rank: number } | null
    fused:    { score: number; rank: number }
    reranker: { score: number; rank: number } | null
  }
  metadata: Record<string, unknown>
}
```

`null` distinguishes "stage did not run" from "stage scored it zero". The UI must render those
differently — a disabled stage is not a zero score.

### 6.2 Pipeline trace

```ts
interface PipelineStage {
  name: 'embedding' | 'dense' | 'sparse' | 'fusion' | 'reranker' | 'generation'
  status: 'ok' | 'skipped' | 'error'
  latency_ms: number
  candidates_in: number | null
  candidates_out: number | null
}
```

Drives the pipeline visualisation. **Stages with `status: 'skipped'` render greyed out.**
The visualisation must reflect what actually executed — never animate a stage that did not run.

### 6.3 Query response

```ts
interface QueryResponse {
  answer: string
  abstained: boolean           // true when the model declined for lack of grounding
  chunks: RetrievedChunk[]
  pipeline: PipelineStage[]
  tokens: { prompt: number; completion: number }
  latency: { retrieval_ms: number; generation_ms: number; total_ms: number }
  request_id: string
}
```

### 6.4 Evaluation run

```ts
interface EvaluationRun {
  run_id: string
  config: { chunk_size: number; top_k: number; retriever: 'dense'|'sparse'|'hybrid'; reranker: boolean }
  metrics: { precision_at_k: number; recall_at_k: number; mrr: number; hit_rate: number
             semantic_similarity: number; faithfulness: number | null }
  per_question: Array<{ id: number; hit: boolean; reciprocal_rank: number }>
  dataset_size: number
  created_at: string
}
```

`faithfulness` is `null` when no LLM judge key is configured — a missing metric must be
absent, never silently zero.

---

## 7. Non-Functional Requirements

| Concern | Target | Rationale |
|---|---|---|
| Retrieval latency (p95) | < 150 ms | measured 42–64 ms today; leaves headroom for reranking |
| End-to-end query (p95) | < 3 s | dominated by the LLM call |
| Cold start | < 15 s | embedding model load dominates; must be a readiness gate |
| Availability | best-effort | portfolio project; no SLA |
| Concurrency | 10 req/s | single container, rate-limited |
| Secrets | env only | never in the repo; `.env` is git-ignored |
| CORS | explicit origin allowlist | wildcard is unacceptable with a public API |
| Rate limiting | per-IP token bucket | the LLM call costs real money |

---

## 8. Failure Modes

| Failure | Detection | Behaviour |
|---|---|---|
| Index missing | `FileNotFoundError` at startup | 503 with actionable message |
| `GROQ_API_KEY` unset | `EnvironmentError` at construction | 503; retrieval-only mode still usable |
| Groq rate limit | `RateLimitError` | exponential backoff, 3 attempts, then 429 to client |
| Groq auth failure | `AuthenticationError` | fail fast, no retry — retrying a bad key is waste |
| Corpus lacks answer | top score below threshold | abstain; surface as a correct outcome, not an error |
| Stale eval labels | CI resolution check | build fails before metrics can mislead |
| Slow reranker | latency budget exceeded | degrade to fused ranking, mark stage `skipped` |

---

## 9. Out of Scope (v1)

- Multi-tenancy and authentication
- Document upload through the UI (corpus is managed via scripts)
- Fine-tuning or training
- Streaming evaluation runs (batch only)
- Vector DB beyond FAISS (Pinecone/Weaviate adapters are future work)

---

## 10. Future Scope

- Adapters for alternative vector stores behind the existing store interface
- Query rewriting / HyDE as an optional pre-retrieval stage
- A/B traffic splitting between configurations
- Regression alerts when a benchmark drops below the last accepted run
- Human-in-the-loop labelling UI to grow the dataset beyond 15 questions

---

## 11. Open Questions

1. **Corpus.** The current corpus is 3 CS-notes files / 23 chunks. The mockup's example
   ("What is the leave policy?") implies HR documents. A 23-chunk corpus makes Precision@5
   structurally weak — with one relevant chunk per question, max P@5 is 0.2. Should the
   corpus grow before benchmarking, and to what?
2. **Reranker.** Wire it live at ~500 ms CPU cost, or keep it evaluation-only?
3. **Dataset size.** 15 questions is small for stable metrics; a single question shifts MRR by
   ~6.7 points. Grow to 50+ before drawing conclusions from benchmarks?
