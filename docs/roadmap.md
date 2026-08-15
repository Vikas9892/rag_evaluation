# Roadmap

**Status legend:** ✅ done · 🟡 partial · ⬜ not started · ⛔ blocked

> **Provenance.** The milestone numbering used throughout the UI (`PendingPanel`
> says "Milestones 6–8", "Milestone 15") originated in a planning brief that was
> never committed — it lived only in session history. This file reconstructs it
> and pins each milestone to what is actually in the tree, verified on
> 2026-08-15. Where the plan and the code disagree, the code is described and the
> deviation is recorded.

---

## Master goal

An engineering platform to **build, evaluate, benchmark and visualise**
Retrieval-Augmented Generation systems — not a chatbot, not a RAG demo.

The distinction drives the product's central constraint (`product_spec.md` §2):
accuracy metrics require ground truth, so Precision@K / Recall / MRR belong on
the labelled-dataset surface and **never beside an ad-hoc query**. The Query
surface carries observability only — per-stage scores, latency, tokens,
retriever agreement.

---

## Phase 1 — Product design

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 0 | Re-anchor ground truth to content spans + CI invariant | ✅ | `93634ce`, `evaluation/ground_truth.py`, `tests/test_ground_truth.py` |
| 1 | `docs/product_spec.md` — vision, journey, features, NFRs, future scope | ✅ | `5a57929` |
| 2 | Frontend architecture + directory contract | ✅ | `6dc7775`, `docs/frontend_architecture.md`, ADR `008` |

**Milestone 0 was inserted ahead of the plan.** Labels anchored to positional
chunk IDs silently re-pointed when chunking changed — MRR fell 1.000 → 0.143
with no error raised, and every test still passed because they use fixtures
rather than the shipped dataset. Building a dashboard on numbers known to be
wrong was the alternative.

## Phase 2 — Frontend foundation

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 3 | Next.js · TypeScript · Tailwind · shadcn/ui · TanStack Query · ESLint · Prettier | ✅ | `a6a261a` |
| 4 | Layout + six routes (`/`, query, evaluation, benchmarks, settings, about) | ✅ | `4f0c4d9` |
| 5 | Shared components — Card, Spinner, Skeleton, Toast, Error Boundary | ✅ | `e7d7822`, `45f6653` |

**Milestone 5 was deliberately deferred past Milestone 6.** Built in the
abstract it would guess at loading/error/empty states; built after the API
client it is shaped by real ones — real 503s from an unbuilt index, real
timeouts. The error taxonomy in Phase 3 now gives each component concrete cases.

## Phase 3 — API integration

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 6 | `services/api.ts` — typed client for `POST /query`, `POST /stream`, `GET /health`, `GET /metrics` | ✅ | `4f0c4d9`, `7f7ce4c` |
| 7 | Error handling — retry, loading, empty state, network failure, timeout | ✅ | `45f6653` — components and policy exist; first consumer lands with M8 |

Milestone 6 also required backend changes: `/health` and `/metrics` returned
bare `dict`, so FastAPI emitted an empty schema and `openapi-typescript`
generated types that said nothing — for exactly the two endpoints the milestone
needed. Both now have Pydantic response models.

The error taxonomy (`services/api-error.ts`) classifies failures by whether a
retry could plausibly succeed:

```
network · timeout · rate_limited · server            → retry
cancelled · bad_request · not_found · unavailable · parse → don't
```

`unavailable` (503) means an unbuilt index or an unset `GROQ_API_KEY`. Neither
self-heals; retrying only delays telling the user what is actually wrong.
`cancelled` exists because a caller abort — navigation, a superseded query — is
not a failure and must never render as one.

The UI half landed with M5, since the two are the same work. `ErrorState` maps
each kind to copy through a total `Record`, so adding a kind to the taxonomy
fails to compile until someone decides what the user should be told about it.
`cancelled` maps to `null` — an aborted request is not a failure — and the
server's `detail` is surfaced only where it is actionable, never for a 5xx.

The `QueryClient` default now consults `ApiError.retryable` rather than retrying
everything once, so the policy lives in one place instead of being restated per
hook. No page consumes these yet; the first real consumer is M8.

## Phase 4 — Query experience

| # | Milestone | Status | Notes |
|---|---|---|---|
| 8 | Question input — autocomplete, history, clear | ✅ | `54b39df`, `b452fab` — `/query?q=…&top_k=10&retriever=dense` |
| 9 | Streaming answer via `/stream` | ✅ | `7a929ea`, `e3484b9` |
| 10 | Answer UI — answer, confidence, sources, latency | 🟡 | answer, latency and time-to-first-token render; confidence and per-source attribution do not |

M9 required a backend change: the SSE contract closed with a bare
`{"type": "done"}`, so moving the UI onto `/stream` would have dropped the
`request_id` and the latency breakdown that `POST /query` returns. `done` now
carries both, plus time-to-first-token, which only the streaming path can
measure. Streamed queries are also counted in `/metrics` now — they were
invisible there, so `total_queries` would have read 0 once the UI switched.

A measurement worth keeping: on a short answer the first token arrived at
532 ms of 545 ms total generation. Groq buffered nearly the whole response, so
streaming bought almost nothing in perceived latency here. It will matter on
long answers; on short ones it is close to theatre.

**The third blocker is cleared.** The settings placeholder promised
`/query?q=…&top_k=10&retriever=hybrid`; `retriever` became a request parameter
in `88b4672` and the selector shipped in `b452fab`. The settings *page* is still
a placeholder — the controls live on the query page, where they are used — and
its reranker toggle stays blocked on open decision 2.

## Phase 5 — Retrieval visualisation

| # | Milestone | Status | Notes |
|---|---|---|---|
| 11 | Retrieved chunks — rank, similarity, source, chunk, metadata | ✅ | `b850d77` |
| 12 | Pipeline visualisation (query → embedding → dense → sparse → fusion → reranker → LLM) | ⬜ | needs `PipelineStage` (spec §6.2), which is not built |

**The M11 blocker is cleared.** `HybridRetriever` no longer discards component
ranks: every result carries `scores` with `dense | sparse | fused | reranker`,
and `retriever` is now a per-request choice, so the settings page can keep the
promise it has been making since M4.

One refinement to the spec's wording. §6.1 glosses `null` as "stage did not
run", but once a stage *can* run and still miss a chunk, that is two different
facts sharing one representation. Per chunk, `null` means "this stage did not
rank this chunk"; whether the stage ran at all is answered by the response's
`retriever` field. The UI needs both to render the distinction the spec asks
for.

A live query shows why the table is worth building: dense's rank-1 chunk was
never surfaced by sparse (fused rank 3), while sparse's rank-1 chunk was dense's
rank 9 (fused rank 2). The retrievers disagree substantially.

The table leads with **rank**, not score, because rank is the only thing
comparable across stages: dense is cosine (~0.5), sparse is BM25 (unbounded,
often >1), fused is an RRF sum (~0.03). Any shared visual scale would assert a
comparison that does not exist, so there are no bars and no heat colours.

Columns cover only the stages the chosen strategy runs — a dense query has no
BM25 column, because a column of dashes reads as "BM25 found nothing" rather
than "BM25 was not asked". Within hybrid, a dash *does* mean the retriever
missed that chunk, and the caption says so.

**What it immediately showed.** On "What is ACID?", dense alone ranks the ACID
Properties section first; hybrid demotes it to third because BM25 never
surfaced it. Fusion is losing to its own dense half on this query. Whether that
generalises is exactly what Milestone 15 would answer, and cannot at this corpus
size.

The reranker stays absent from every trace because it is not wired into the
live path — open decision 2 below.

## Phase 6 — Evaluation dashboard

| # | Milestone | Status | Notes |
|---|---|---|---|
| 13 | Metrics cards — Precision@K, Recall, MRR, latency | ⬜ | |
| 14 | Charts — bar, trend, benchmark comparison | ⬜ | |
| 15 | Benchmark matrix — chunk size × top-K × retriever | ⛔ | **Corpus too small to discriminate** |

**The M15 blocker.** At 19 chunks and 15 questions, MRR is already 1.00, so
every configuration scores identically and the matrix would discriminate
nothing. Precision@5 is structurally capped near 0.20–0.40 because each question
has one or two relevant chunks while five are retrieved. Growing the corpus and
dataset is a prerequisite, not a polish step.

## Phase 7 — Backend improvements

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 16 | Caching (Redis) | ⬜ | no Redis dependency |
| 17 | Structured logging — request ID, latency, retrieved chunks, token usage | 🟡 | per-request UUID in `services/rag_service.py`, surfaced as `QueryResponse.request_id`; not all fields logged structurally |
| 18 | Prometheus metrics | ⬜ | `/metrics` is in-process JSON counters, not a Prometheus exposition |
| 19 | Deep health checks — Groq, FAISS, disk, memory | ⬜ | `/health` returns `healthy` unconditionally (deliberate for load-balancer probes; the deep check is a separate endpoint) |
| 20 | Rate limiting | ⬜ | retry/backoff exists in `generation/generator.py` for the Groq client; no API-level limiting |

## Phase 8 — Deployment

| Target | Planned | Actual | Status |
|---|---|---|---|
| Backend | Render | AWS Lambda — `aws/lambda_handler.py`, `aws/template.yaml` (SAM), plus `Dockerfile` / `docker-compose.yml` | ✅ deviates |
| Frontend | Vercel | not deployed | ⬜ |

Environment: `GROQ_API_KEY` (backend), `NEXT_PUBLIC_API_URL` (frontend),
`ALLOWED_ORIGINS` (CORS allowlist, added in M6).

## Phase 9 — Documentation

| Item | Status |
|---|---|
| README | ✅ |
| `docs/architecture.md` | ✅ |
| ADRs `001`–`008` | ✅ |
| API / deployment / trade-offs / benchmarks | 🟡 covered across the above, not as standalone docs |

## Phase 10 — Portfolio polish

⬜ Demo GIF · screenshots · architecture diagrams · benchmark report · deployment guide.

Browser screenshots were unavailable in earlier sessions (Chrome extension not
connected); verification fell back to rendered HTML.

---

## Working agreement

Each milestone: design discussion before code · explain why, trade-offs,
scaling, failure modes, security · end with passing tests, lint, format,
updated README and architecture · suggested commit message · **wait for
approval before the next milestone**. Clean Architecture and SOLID; dependency
injection where it earns its place; no unrelated code touched.

## Open decisions

These were raised before Milestone 2 and are still unanswered:

1. **Corpus size.** Stay at 19 chunks of CS notes, or grow it? The original
   mockup's "leave policy" example implies HR documents. This gates M15.
2. **Reranker.** Wire the cross-encoder into the live path (~500 ms on CPU), or
   keep it evaluation-only with the stage rendered greyed out? Currently
   implemented but not live — the About page says so explicitly.
3. **Dataset size.** ~50 questions was proposed to make benchmark comparisons
   less noisy.

## Suggested next step

**Milestone 12 — the pipeline visualisation**, which needs one backend piece
first: `PipelineStage` from spec §6.2, carrying each stage's status, latency and
candidate counts. Without it the diagram would have to guess which stages ran
and how long they took, and the spec is explicit that it must never animate a
stage that did not execute.

Alternatively **grow the corpus**, which is the prerequisite for the whole of
Phase 6. Three separate findings now point at it: MRR pinned at 1.00, BM25's IDF
flooring to zero on a term in half the corpus, and the hybrid-versus-dense
result above being a single anecdote rather than a measurement.

M10's remaining half — whether the model abstained for lack of grounding — is
small and independent of both.

---

## A note on process

Roughly 1,900 lines of frontend work sat uncommitted for three days and were
nearly lost when OneDrive deleted the working tree and corrupted `.git`. The
work was recovered from GitHub plus session transcripts, but three things had no
transcript record because they were produced by commands rather than file
writes: `types/api.generated.ts` (from `npm run gen:api`), the `msw` dev
dependency (from `npm install`), and Prettier's formatting pass. All three are
now committed. Commit at each milestone boundary, as the working agreement
already says.
