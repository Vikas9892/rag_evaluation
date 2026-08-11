# ADR 008 — Frontend Architecture (Next.js, generated types, TanStack Query)

**Status:** Accepted
**Date:** 2026-08

---

## Context

The backend is a FastAPI service that already exposes `/query`, `/stream`, `/health` and
`/metrics`.  The platform now needs a dashboard that shows retrieval traces, evaluation
metrics and benchmark comparisons.

The frontend is not a thin display layer.  It renders latency measurements, per-stage
retrieval scores and accuracy metrics — numbers whose credibility is the product.  Every
architectural choice below is judged against one question: *does this keep the displayed
numbers faithful to what the backend actually did?*

## Decision

1. **`frontend/` lives in this repository**, alongside the Python backend.
2. **Next.js (App Router) + TypeScript + Tailwind + shadcn/ui.**
3. **The browser calls FastAPI directly.**  No Next.js route-handler proxy.
4. **TypeScript API types are generated from the FastAPI OpenAPI schema.**  They are never
   hand-written.
5. **TanStack Query owns server state.**  No global client-state store.
6. **Vitest + React Testing Library** for tests.

## Rationale

### Direct API calls, not a BFF proxy

A Next.js route handler proxying to FastAPI would sidestep CORS and could hide secrets.
Neither benefit applies here: `GROQ_API_KEY` is held by the backend and never reaches the
browser, so there is nothing to hide.  The cost is real — an extra network hop on every
request.

This platform displays latency as a headline metric.  A proxy would inflate every measured
number by its own overhead, so the dashboard would report a latency the API does not have.
Direct calls keep the measurement faithful.  The price is that CORS must be configured
explicitly with an origin allowlist rather than avoided.

### Generated types, not hand-written interfaces

A hand-maintained `interface QueryResponse` is a mirror of the backend's Pydantic schema.
Mirrors drift.  When `SourceInfo` gains a field or `score` changes meaning, the TypeScript
interface still compiles, the UI still renders, and the numbers are quietly wrong.

This is exactly the failure recorded in ADR-006's follow-up and fixed in
`evaluation/ground_truth.py`: ground-truth labels mirrored chunk positions, drifted when
chunking changed, and corrupted every metric without raising an error.  The lesson
generalises — **do not hand-maintain a copy of something that can change independently.**

`openapi-typescript` reads FastAPI's `/openapi.json` and emits types.  Backend change →
regenerate → the frontend fails to compile at exactly the call sites that need attention.
Drift becomes a build error instead of a wrong number on a dashboard.

### TanStack Query for server state

Retrieval results, metrics and benchmark runs are server state: they live remotely, can go
stale, and need caching, retries and invalidation.  Query text, expanded rows and theme are
client state, owned by React.

Treating server state as client state is the common failure — it produces hand-rolled
loading booleans, manual refetch calls, and stale data with no invalidation story.  Keeping
the two separate means no Redux or Zustand is needed at this scale.

### Server vs client components

Layout, navigation and `/about` are server components.  Anything that calls the API is a
client component: the query page mutates on submit and consumes an SSE stream, which is
inherently client-side.  The boundary is drawn at the network call, not by page.

## Consequences

- CORS must be configured on the FastAPI app with an explicit origin allowlist before the
  first browser request succeeds.  `api/app.py` currently has no CORS middleware.
- `npm run gen:api` must be re-run after backend schema changes.  Forgetting to is caught
  by the type checker, not silently ignored.
- The generated types file is committed, so CI and Vercel builds do not need a running
  backend.
- Deploying to Vercel requires the root directory set to `frontend/`, since the repository
  root is a Python project.
- shadcn/ui copies component source into the repo rather than adding a dependency.  We own
  the code and it cannot churn under us; we also do not get upstream fixes automatically.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| Next.js route handlers as a BFF proxy | Adds a hop to every request; inflates the latency numbers the product exists to report |
| Hand-written TypeScript interfaces | Silent drift from the backend schema — the exact bug class fixed in `ground_truth.py` |
| Redux / Zustand | Server state is not client state; TanStack Query covers caching, retries and invalidation |
| Separate repository for the frontend | A full-stack change would span two PRs; contract changes could merge out of order |
| Vite + React SPA | Loses streaming-friendly routing and Vercel deployment ergonomics |
| MUI / Chakra | Heavier runtime and harder to restyle than Tailwind + vendored shadcn components |
