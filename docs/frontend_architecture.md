# Frontend Architecture

**Status:** built through Milestone 7 — see [roadmap](roadmap.md) for what remains
**Decisions:** [ADR 008](decisions/008-frontend-architecture.md)

This document was written in Milestone 2 as a design, before the tree existed. The
structure below now describes the code as built; where the two ever disagree, the code
is wrong or this file is stale, and one of them gets fixed.

---

## Layering

Clean Architecture applied to a frontend: dependencies point inward, and no layer knows
about the one above it.

```
  app/            routing, layout, page composition
    │  depends on
    ▼
  components/     presentational; props in, events out; no fetching
    │  depends on
    ▼
  hooks/          React-facing state: useQuery/useMutation wrappers
    │  depends on
    ▼
  services/       API calls; the only layer that knows a network exists
    │  depends on
    ▼
  types/          generated from the FastAPI OpenAPI schema
```

The rule that keeps this honest: **only `services/` may reference `fetch` or a URL.**  A
component that fetches is a component that cannot be tested without a network, and a
component that formats a metric is reusable everywhere.

## Directory responsibilities

| Path | Holds | Must not |
|------|-------|----------|
| `app/` | routes, layouts, page shells | contain business logic or fetch calls |
| `components/ui/` | vendored shadcn primitives (Button, Card, Skeleton) | be edited for feature-specific needs |
| `components/` | feature components (RetrievalTable, PipelineView, MetricCard) | call the API directly |
| `hooks/` | `useQueryRag`, `useHealth`, `useBenchmarks` | render JSX |
| `services/` | typed API client, SSE stream reader, error mapping | import React |
| `lib/` | pure helpers — formatting, score maths, class merging | perform I/O |
| `types/` | `api.generated.ts` plus hand-written view models | be edited by hand for API shapes |

## Data flow — a single query

```
  QueryPage (client component)
      │  question, top_k
      ▼
  useRagQuery()                    ← TanStack useMutation
      │
      ▼
  services/api.queryRag()          ← the only layer touching the network
      │  POST /query
      ▼
  FastAPI  (localhost:8000 / Render)
      │  QueryResponse
      ▼
  types/api.generated.ts           ← compile-time contract, generated from OpenAPI
      │
      ▼
  AnswerCard · RetrievalTable · PipelineView · LatencyStrip
```

Errors travel the same path in reverse: `services/` maps HTTP status to a typed
`ApiError` (`network` / `timeout` / `unavailable` / `rate_limited` / `server`), the hook
exposes it, and components render per-variant states rather than a generic "something went
wrong".  A 503 from a missing index and a 429 from rate limiting need different copy —
one is a setup problem, the other is a wait-and-retry.

## State ownership

| State | Owner | Why |
|-------|-------|-----|
| Query results, metrics, benchmarks, health | TanStack Query | remote, cacheable, can go stale |
| Streaming tokens | component `useState` | ephemeral, dies with the request |
| Question text, expanded rows, active tab | component `useState` | pure UI |
| Query history | `localStorage` via a hook | survives reload, never sent to the server |
| top-K, retriever, reranker toggle | URL search params | shareable and back-button correct |

Putting configuration in the URL is deliberate: `/query?q=...&top_k=10&retriever=hybrid`
reproduces a result exactly, which matters for a tool whose output is evidence.

## Type generation

```
FastAPI  ──/openapi.json──►  openapi-typescript  ──►  types/api.generated.ts
```

```bash
npm run gen:api     # regenerate after any backend schema change
```

The generated file is committed so CI and Vercel build without a running backend.  It is
never edited by hand — a backend change that is not regenerated surfaces as a TypeScript
error at the call site, not as a wrong number on screen.

## Routes

| Route | Rendering | Data |
|-------|-----------|------|
| `/` | server shell + client status widget | `GET /health`, `GET /metrics` |
| `/query` | client | `POST /query`, `POST /stream` |
| `/evaluation` | client | evaluation run endpoints (Phase 6) |
| `/benchmarks` | client | benchmark comparison endpoints (Phase 6) |
| `/settings` | client | URL params + `GET /config` |
| `/about` | server, static | none |

## Testing

| Layer | Tool | What is asserted |
|-------|------|------------------|
| `lib/` | Vitest | pure functions: formatting, score maths |
| `services/` | Vitest + MSW | request shape, status→`ApiError` mapping, timeouts |
| `hooks/` | Vitest + RTL | loading/error/success transitions |
| `components/` | RTL | rendering per state, including empty and error |

Components are tested against mocked hooks, never a live backend — the same discipline that
keeps 90% of the Python suite offline (ADR 005).

## Environment

| Variable | Where | Example |
|----------|-------|---------|
| `NEXT_PUBLIC_API_URL` | frontend build + runtime | `http://localhost:8000` |
| `ALLOWED_ORIGINS` | backend | `http://localhost:3000,https://<app>.vercel.app` |

`NEXT_PUBLIC_*` variables are inlined into the client bundle and are public by definition.
Nothing secret may ever use that prefix.

## CORS

Resolved.  `api/app.py` registers `CORSMiddleware` with an explicit allowlist from
`ALLOWED_ORIGINS` (default `http://localhost:3000`), `allow_credentials=False`, and only
the verbs the client issues (`GET`, `POST`, `OPTIONS`).  `*` is accepted as an operator
override but logs a warning: a wildcard on an endpoint that spends Groq budget lets any
page on the internet spend it.

## Error taxonomy

`services/api-error.ts` maps every failure to a kind, because the UI needs two answers a
status code alone cannot give: what to tell the user, and whether retrying can help.

| Kind | Source | Retryable | Why |
|------|--------|-----------|-----|
| `network` | fetch rejected, not aborted | ✅ | transient connectivity |
| `timeout` | deadline exceeded, or 504 | ✅ | may succeed when load drops |
| `cancelled` | caller aborted | ❌ | not a failure; never shown as one |
| `bad_request` | 400, 422 | ❌ | the request itself is wrong |
| `not_found` | 404 | ❌ | |
| `rate_limited` | 429 | ✅ | resolves by waiting |
| `unavailable` | 503 | ❌ | unbuilt index or missing key — does not self-heal |
| `server` | 5xx | ✅ | may be transient |
| `parse` | body was not the expected shape | ❌ | retrying returns the same body |

`unavailable` being non-retryable is deliberate and mirrors
`GroqGenerator._call_with_retry` on the backend, which retries rate limits and connection
errors but fails fast on auth and bad requests.  Retrying a 503 three times only delays
telling the user the index is not built.

Classification reads `signal.aborted` and `signal.reason` rather than sniffing the thrown
exception: Node and browsers disagree on whether an aborted fetch throws `TimeoutError`,
`AbortError`, or a `TypeError` wrapping either, but the signal's state is specified.

## Rendering a failure

| Situation | Component | Why |
|---|---|---|
| A request failed | `ErrorState` | the failure is data; the page stays mounted and keeps its retry affordance |
| A request was cancelled | nothing | not a failure — the user navigated away or superseded the query |
| Zero results | `EmptyState` | a valid answer; retrying returns zero again |
| A component threw while rendering | `ErrorBoundary` | a bug, not a response — React catches only what render throws |

The boundary and the error state are not interchangeable. A rejected fetch settles outside
render and never reaches a boundary, and a boundary unmounts its subtree, which would take
the retry button with it. `ErrorBoundary` takes `resetKeys` — usually the pathname — because
one that caught an error on one route would otherwise stay broken on the next.

`ErrorState` maps kinds to copy through a total `Record`, so a new kind fails to compile
until its copy exists. The server's `detail` is rendered only where it is written for a
user and is actionable (422 validation, 503 unbuilt index); a 5xx gets fixed copy, because
its detail can carry internals that belong in a log.

Retry policy lives once, on the `QueryClient` default, which consults `ApiError.retryable`.
A hook overrides it only when it has a reason to.
