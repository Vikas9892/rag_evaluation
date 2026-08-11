# Frontend Architecture

**Status:** Milestone 2 — design only, no code yet
**Decisions:** [ADR 008](decisions/008-frontend-architecture.md)

The structure below is documented now and created in Milestone 3 by `create-next-app`.
Directories are not pre-created, because the generator owns the initial tree.

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

## Known blocker for Milestone 3

`api/app.py` registers no CORS middleware, so the first browser request will fail the
preflight check.  Adding `CORSMiddleware` with an explicit origin allowlist — not `*` —
is the first task of the API-integration milestone.
