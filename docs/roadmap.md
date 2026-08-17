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
| 10 | Answer UI — answer, confidence, sources, latency | ✅ | `abc2d66`, `d2fb86f` — abstention is a contract check on the reply the prompt demands, not an inference |

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
| 12 | Pipeline visualisation (query → embedding → dense → sparse → fusion → reranker → LLM) | ✅ | `662ca3a`, `1b549ac` |

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

### Milestone 12 — and why it is not a chart

The stage list is produced by the backend rather than inferred by the frontend,
because only the retriever knows what it chose to run: a sparse-only query
embeds nothing, and no result set reveals that. Every stage is reported every
time, skipped ones included, so a stage never disappears from the diagram.

**The diagram deliberately contains no chart.** The design system's chart ramp
is achromatic — `oklch(L 0 0)` for all five steps — and the palette validator
fails it as a categorical palette on two counts: every step is below the chroma
floor, and adjacent steps sit at ΔE 6.7 against a normal-vision floor of 15.
Encoding six stage identities in shades that a full-colour reader cannot
separate would be worse than no chart, and inventing hues would mean abandoning
the design system. Identity is in labels, magnitude in numbers, and the finding
in one sentence.

**What it measured immediately.** On a live hybrid query: embedding 381 ms,
dense search 2.6 ms, BM25 0.4 ms, fusion 0.05 ms, generation 603 ms. The
embedding model's forward pass is 38% of end-to-end latency and roughly 99% of
retrieval. The old single "retrieval" number could say retrieval was slow; it
could not say why. If retrieval latency ever needs to come down, the answer is a
smaller or cached embedding model, not a faster index.

## Phase 6 — Evaluation dashboard

| # | Milestone | Status | Notes |
|---|---|---|---|
| 13 | Metrics cards — Precision@K, Recall, MRR, latency | ✅ | `d2fb86f` |
| 14 | Charts — bar, trend, benchmark comparison | ✅ | `d2fb86f` — single-series MRR bars; see the palette note under M12 for why nothing is coloured |
| 15 | Benchmark matrix — chunk size × top-K × retriever | ✅ | `d2fb86f` — retriever × top-K; chunk size needs a re-index per cell and is not swept |

**The M15 blocker turned out not to hold, and that is worth recording.** It was
written when MRR sat at 1.00 for everything. Since the heading-aware chunking and
the sub-threshold merge, the matrix discriminates clearly:

| retriever | MRR @5 | recall @5 |
|---|---|---|
| dense | **1.000** | 1.000 |
| hybrid | 0.913 | 0.967 |
| sparse | 0.806 | 0.900 |

**Dense alone beats the hybrid retriever that is wired as the live default, on
every metric.** BM25 drags fusion down: it is the half that misses, and RRF gives
it an equal vote. This generalises the single anecdote from M11 across 15
questions and 9 configurations.

That is a product decision, not a code change to make unasked — switching the
default is one line, and whether 15 questions justify it is your call. Precision@K
remains structurally capped near 1/K and should not be read as a grade.

The corpus is still small. A result this consistent across 9 configurations is a
direction worth acting on; it is not yet a settled one, and the UI says so.

## Phase 7 — Backend improvements

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 16 | Caching | ✅ | `abc2d66` — in-process, not Redis; see below |
| — | *(deviation)* | | Redis was the plan. It would add a service to operate for a cache one process can hold, and the moment this runs on more than one process the FAISS index would have to be shared too — so the cache is not the first thing that needs distributing. Same argument for the rate limiter. |
| 17 | Structured logging — request ID, latency, retrieved chunks, token usage | ✅ | `abc2d66` — request id, per-stage latency, chunk counts, tokens, retriever |
| 18 | Prometheus metrics | ✅ | `abc2d66` — `/metrics/prometheus`, kept off the JSON `/metrics` the UI reads |
| 19 | Deep health checks — Groq, FAISS, disk, memory | ✅ | `abc2d66` — `/health/deep`; separate from the liveness probe on purpose |
| 20 | Rate limiting | ✅ | `abc2d66` — token bucket on `/query` and `/stream` only |

## Phase 8 — Deployment

| Target | Planned | Actual | Status |
|---|---|---|---|
| Backend | Render | **AWS EC2 `t4g.small`** — Docker behind Caddy, live at <https://vikas-rag.duckdns.org> | ✅ deviates |
| Frontend | Vercel | Vercel, live at <https://rag-evaluation-rosy.vercel.app>, redeploying on every push to `main` | ✅ |

**Render was the plan and does not fit.** The API holds 743 MB resident with the
model and index loaded, against 512 MB on Render's free instance — 45% over. The
alternative was replacing PyTorch with ONNX Runtime in the embedding path, which
is surgery on the one component every number in
[benchmark_report.md](benchmark_report.md) depends on, to save a bill that is
zero either way. EC2 at ~$17/month keeps the retrieval core untouched, and the
live deployment reproduces every quality metric exactly.

**Lambda was the previous actual and does not fit either.** It routes three
endpoints, its `lifespan="off"` means the indexing worker never starts, and
`/var/task` is read-only so SQLite and every index rebuild fail. It remains a
good fit for the query-only service it was written for. Full detail in
[deployment.md](deployment.md).

Environment: `GROQ_API_KEY` (backend), `NEXT_PUBLIC_API_URL` (frontend, inlined
at build time), `ALLOWED_ORIGINS` (CORS allowlist, added in M6),
`STORAGE_EPHEMERAL` (`0` on EC2, since the EBS volume genuinely persists).

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

## Status

Every milestone from 0 to 20 is built, no page shows a placeholder, and the three
open decisions are closed:

1. **Default retriever: dense.** Measured over 53 questions and 18
   configurations, dense beats hybrid at every top-K. RRF gives each retriever an
   equal vote, so fusing with a weaker one drags the ranking below its own better
   half.
2. **Corpus: 148 chunks over 8 documents, 53 labelled questions** (from 19 / 3 /
   15). Large enough that the matrix discriminates and BM25's IDF is no longer
   degenerate.
3. **Reranker: wired, opt-in, and swept.** It is the largest single lever — it
   lifts sparse retrieval by 0.173 MRR — but costs hundreds of milliseconds
   against a 300–600 ms generation step, so it is off by default and selectable
   per request.

See [benchmark_report.md](benchmark_report.md) for the full matrix.

---

# Programme 2 — workspace and evaluation lab

The milestones above built a dashboard over a corpus fixed at build time. This
programme added the other half: a user uploads their own documents and queries
them, over the *same* retriever the lab benchmarks. Its baseline is captured in
[baseline.md](baseline.md).

| Phase | Subject | Status | Where it landed |
|---|---|---|---|
| 0 | Repository audit and baseline | ✅ | `730dec7`, `baseline.md` |
| 1 | Asynchronous document ingestion | ✅ | `3b64edb` queue/worker, `5f2fcc9` API |
| 2 | Document management and lifecycle | ✅ | `e830503`, `6e42941` — real deletion, not a tombstone |
| 3 | Corpus / index isolation | ✅ | `8f81de0` — `index/corpora/<id>/`, retrieval scoped per corpus |
| 4 | Chunking as configuration | ✅ | `c500a3e` — indexing-time, and the UI says so |
| 5 | Query-time retrieval settings | ✅ | `c500a3e`, `36a59bb` |
| 6 | Query flow over an uploaded corpus | ✅ | `5f2fcc9`, `36a59bb` |
| 7 | Source citation and retrieval trace | ✅ | `b850d77`, `1b549ac` (carried from M11/M12) |
| 8 | Workspace UI | ✅ | `463080b`, `f869bfa` |
| 9 | Query UI | ✅ | `36a59bb` |
| 10 | Evaluation Lab | ✅ | `ac03aac`, `583b299` — the existing page kept, then extended |
| 11 | Benchmark comparison and recommendation | ✅ | `34f796f` — with the latency it costs, not a winner |
| 12 | Light / dark / system themes | ✅ | `1c9c3b0` |
| 13 | Design system | ✅ | `components/ui/` — 15 primitives, one styling system |
| 14 | Overview dashboard | ✅ | `24342d0` |
| 15 | Settings, split by when a setting applies | ✅ | `a1e3ede` |
| 16 | About | ✅ | `a1e3ede` |
| 17 | Pydantic schemas, 202 on upload | ✅ | `5f2fcc9`, `api/schemas.py` |
| 18 | Error handling | ✅ | `5f2fcc9`, `6710cef` — 422 bodies now name the field |
| 19 | Testing, unit through E2E | ✅ | `dca40b9`, `7d62400` — 666 Python, 359 frontend, 5 E2E |
| 20 | Upload security | ✅ | `e830503` — type, size, and a filename never trusted as a path |
| 21 | Performance | ✅ | `6710cef`, `f869bfa` — one shared model, stage timings surfaced |
| 22 | Evaluation preserved | ✅ | verified in `baseline.md`; four configurations re-measured |
| 23 | Documentation | ✅ | `4974732`, this file |

**Phase 21 is the one worth reading twice.** Every retriever and the indexing
worker constructed its own `Embedder`, so a process serving eight corpora held
eight identical copies of bge-small — about a gigabyte of resident memory doing
what 130 MB does. `shared_embedder()` is cached by model and device, so a caller
that genuinely wants a different model still gets one.

**Phase 22 held.** Precision@5, Recall@5, hit rate and MRR are identical to the
pre-change baseline, and three further configurations reproduce the benchmark
report to the digit. Retrieval quality was not traded for any of the above.

## Phase 24 — the build nobody was reading

Added after the fact, because the twenty-three phases above were all marked
done while CI had been red the entire time. The badge said so; nobody looked.

| Fix | Commit | What it was |
|---|---|---|
| `python-multipart` undeclared | `a24bc8b` | FastAPI raises when it *builds* an `UploadFile` route, so collection aborted and every API test errored on both Python versions. Installed here as another package's transitive dependency, so only CI could see it. |
| `/settings` needed a Groq key | `aea0d94` | It declared a `RAGService` dependency it never used. Building that constructs the Groq client, so the endpoint answered 503 — the page explaining how a deployment is configured was dead exactly where a reader would look. |
| Duplicated test block | `71fa71d` | The last 82 lines of `test_chunking.py` repeated the preceding 82 verbatim; Python bound the later copy, so a whole test class was shadowed. Ruff's F811 surfaced it. |
| Leaked SQLite connections | `7d62400` | 211 ResourceWarnings per run. `pytest` now errors on `unclosed database`. |
| Ruff and black | `b9c60fb`, `3326ace` | 30 findings and 64 unformatted files. Both now configured and gated by a CI job, with pinned versions. |
| Retrieval needed a Groq key | `76e1b81` | `/config`, `/evaluation` and `/benchmarks` resolved a RAGService and reached through it for `.retriever`, so all three answered 503 with no key — while `/evaluation`'s description says "No LLM calls are made". The whole Evaluation Lab was unreachable to anyone who had not signed up for Groq, to read numbers produced entirely by retrieval. |
| Deleted documents stayed searchable | `21054d9` | DELETE removes the chunks in the index at that moment; a job already running writes its chunks *after*. Deleting during PARSING left 13 chunks against 0 document records — the workspace showed an empty knowledge base while queries answered from the deleted file. |
| Deleted files stayed on disk | `b353c2b` | The unlink was attempted inside a try/except that logged and carried on, and the reply said "Document, file and chunks removed" either way. Windows refuses to unlink a file the indexer holds open, so the bytes survived a deletion the user was told had happened. |
| One log file, 33 writers | `eca312d` | Every `get_logger` call built its own `RotatingFileHandler` over the same path, so rotation raced with itself. |

The last three were found by driving the running API rather than by reading it
— uploading a document and deleting it mid-index, then asking what was left on
disk and in the corpus. None of them had a failing test, because each lived in a
window the tests never opened.

Three of the first five were invisible locally and only ever failed in CI. The
common shape: a check that ran only where it could not fail. `GROQ_API_KEY` is
set on this machine and unset on the runner, so the pre-push command is now

```bash
env -u GROQ_API_KEY pytest --cov=. --cov-fail-under=85
```

**The `/settings` fix cost coverage, and that was worth noticing.** The endpoint
had been the only thing exercising the real-corpus service builder, by accident.
`tests/test_dependencies.py` now covers it deliberately — building over the real
evaluation corpus, the cache that stops a query paying for an index load twice,
404 against 422 corpus resolution, and the 503 with no key. `api/dependencies.py`
went 67% → 90%; the suite went 651 → 666 tests and 93% → 94%.

## What is left

- **Uploads on the live instance are not durably queued.** The EBS volume
  persists them, so a restart no longer loses documents, but the queue is still
  an in-process thread — a restart mid-index strands a job, which startup
  recovery then requeues. `REDIS_URL` is the fix and costs another service.
- **Generation quality is unmeasured.** Every metric here is retrieval-only. The
  generation evaluator exists and costs LLM calls, so it has no endpoint yet.
- **A demo GIF.** Screenshots are captured headlessly into `docs/screenshots/`;
  a recorded walkthrough is not.
- **The end-to-end suite is not in CI.** The frontend job (`655a02e`) runs the
  typecheck, lint, format check, 359 unit tests and the build; Playwright stays
  local because it needs the model weights and both servers running to re-cover
  ground the unit suite already holds. It remains the only check that depends on
  somebody remembering.

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
