# Deployment

**The recommended free path is [Hugging Face Spaces + Vercel](#free-deployment-hugging-face-spaces--vercel).**
The AWS Lambda template below predates the workspace programme and serves only
the query half — see [Lambda's limits](#what-lambda-cannot-do) before choosing it.

The backend runs on AWS Lambda behind API Gateway (`aws/template.yaml`). The
frontend is a static Next.js build intended for Vercel.

The two are deployed independently and know about each other through exactly two
environment variables. Getting those wrong is the only way this fails, so they
are the first thing to check.

## The two variables

| Variable | Set on | Value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | frontend, at **build** time | the backend's public URL, no trailing slash |
| `ALLOWED_ORIGINS` | backend | the frontend's public URL, comma-separated for several |

They point at each other. A frontend built against the wrong API URL cannot be
fixed by redeploying the backend — `NEXT_PUBLIC_*` is inlined into the client
bundle at build time, so it needs a rebuild.

`ALLOWED_ORIGINS` is not decoration. The browser calls the API directly, so this
is the only thing between an endpoint that spends Groq budget and any page on
the internet. `*` is accepted and logs a warning; it should not be used on a
deployment that costs money.

## Backend

```bash
sam build --template aws/template.yaml
sam deploy --guided        # first time only, then: sam deploy
```

Set on the function:

```
GROQ_API_KEY=...                                   # generation only
ALLOWED_ORIGINS=https://<your-app>.vercel.app
RATE_LIMIT_PER_SECOND=1                            # optional, defaults shown
RATE_LIMIT_BURST=10
```

**The index ships with the deployment.** `index/` is gitignored and built by
`scripts/build_embeddings.py` then `scripts/build_index.py`. It must exist in
the deployment package or every request answers 503 with "Index not available" —
which `/health/deep` reports as a failing `index` check rather than leaving you
to guess.

The rate limiter and the evaluation cache are both per-process. Lambda gives
each concurrent execution its own process, so the effective rate limit is the
configured rate times the concurrency. If that matters, cap reserved concurrency
or move the limiter to shared state.

## Frontend

```bash
cd frontend
vercel                     # first time: links the project
vercel --prod
```

Set in the Vercel project, for the environments you build:

```
NEXT_PUBLIC_API_URL=https://<api-id>.execute-api.<region>.amazonaws.com/prod
```

`vercel.json` pins the framework, the build and install commands, and three
response headers. It deliberately does not set `NEXT_PUBLIC_API_URL`: committing
a deployment's API URL into the repo makes every environment share one backend.

## Verifying a deployment

In order, because each step's failure looks like the next step's:

```bash
curl -s "$API/health"                     # process is up
curl -s "$API/health/deep"                # index present, key set, disk free
curl -s "$API/config"                     # corpus size — 0 chunks means no index
curl -sD- -o /dev/null -X POST "$API/query" \
  -H 'Content-Type: application/json' \
  -H "Origin: https://<your-app>.vercel.app" \
  -d '{"question":"test"}' | grep -i access-control-allow-origin
```

If the last command prints no `access-control-allow-origin` header, the browser
will block the response even though `curl` sees a 200. That is the single most
common deployment failure, and it looks like a frontend bug from the browser.

## What is not automated

There is no CI deployment step. CI builds the index and runs the tests; shipping
is manual and deliberate, because both deploys carry credentials this repository
does not hold.

---

# Free deployment: Hugging Face Spaces + Vercel

The whole platform, both modes, at no cost.

## Why this pairing

The binding constraint is memory. With the model and index loaded the API holds
**~743 MB resident** — PyTorch is 490 MB on disk before a single weight is read.

| Host | Free RAM | Verdict |
|---|---|---|
| **HF Spaces (CPU basic)** | ~16 GB | fits with room to spare |
| Render free | 512 MB | **OOM**, ~45% over |
| Fly.io free | 256 MB | no |

Render would mean replacing PyTorch with ONNX Runtime to fit. That is real work
on the embedding path — the component every number in
[benchmark_report.md](benchmark_report.md) depends on — to save a bill that is
zero either way. Spaces needs no change to the retrieval core, so Recall 0.962
and MRR 0.878 stay provably the numbers the repo reports.

Spaces also sleeps after ~48 hours idle rather than 15 minutes, which matters
when the URL is in a job application.

## Step 1 — the backend on Spaces

Create a Space: **SDK = Docker**, hardware = CPU basic (free), visibility public.

Add `README.md` front-matter **at the repository root of the Space** — Spaces
reads its configuration from there:

```yaml
---
title: RAG Evaluation Platform
emoji: 🔍
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 8000
---
```

`app_port: 8000` matches the `EXPOSE` in the `Dockerfile`. Without it Spaces
looks for 7860 and the Space never becomes healthy.

Push the repository to the Space remote:

```bash
git remote add space https://huggingface.co/spaces/<user>/<space-name>
git push space main
```

Then set two **Space secrets** (Settings → Variables and secrets):

| Name | Value |
|---|---|
| `GROQ_API_KEY` | your key — a *secret*, not a variable, so it is not shown in the UI |
| `ALLOWED_ORIGINS` | `https://<your-app>.vercel.app` (fill in after step 2, then restart) |

The build takes several minutes: it installs PyTorch, downloads the embedding
model and builds the 148-chunk index, all at image-build time. That is
deliberate — it means the first visitor waits for none of it.

## Step 2 — the frontend on Vercel

```bash
cd frontend
vercel            # first run links the project
vercel --prod
```

Set the **root directory to `frontend/`** in the Vercel project, and one
environment variable:

```
NEXT_PUBLIC_API_URL=https://<user>-<space-name>.hf.space
```

No trailing slash. It is inlined at build time, so changing it needs a rebuild,
not a restart.

Then go back and set `ALLOWED_ORIGINS` on the Space to the Vercel URL, and
restart the Space. The two only know each other through these two variables;
getting them wrong is the only way this fails.

## Step 3 — verify, in this order

```bash
API=https://<user>-<space-name>.hf.space

curl -s "$API/health"        # process up
curl -s "$API/health/deep"   # index present, key set, disk free
curl -s "$API/config"        # expect 148 indexed_chunks — 0 means no index
curl -s "$API/evaluation?top_k=5&retriever=dense" | head -c 200
```

Then the CORS check, which is the failure that looks like a frontend bug:

```bash
curl -sD- -o /dev/null -X POST "$API/query" \
  -H 'Content-Type: application/json' \
  -H "Origin: https://<your-app>.vercel.app" \
  -d '{"question":"What is the TCP three-way handshake?"}' \
  | grep -i access-control-allow-origin
```

No header means the browser blocks a response `curl` sees as a 200.

## What this costs you

**Uploads do not survive a restart.** A free Space has an ephemeral filesystem,
so uploaded documents, `documents.db` and rebuilt indexes are lost when the
Space restarts or rebuilds. Concretely:

| Surface | On a free Space |
|---|---|
| Query, Evaluation, Benchmarks, Overview, Settings, About | permanent — the benchmark corpus is baked into the image |
| Workspace upload → index → query | works, until the next restart |

The benchmark corpus is unaffected because it is built into the image rather
than written to a volume. Persistent storage is a paid Spaces add-on if the
Workspace half ever needs to outlive a restart.

## What Lambda cannot do

Recorded because the template above is still in the repository and looks
deployable:

1. **It routes three endpoints.** `aws/template.yaml` declares `HttpApi` events
   for `/query`, `/health` and `/metrics` only. `/documents`, `/corpora`,
   `/queue`, `/evaluation`, `/benchmarks`, `/config`, `/settings`,
   `/health/deep` and `/stream` would all 404.
2. **The indexing worker never starts.** `aws/lambda_handler.py` sets
   `lifespan="off"`, and the lifespan is what calls `start_indexing_worker()`.
   An upload would return its 202 and sit at `QUEUED` for ever. The setting is
   correct for Lambda — a background thread cannot outlive an invocation — which
   is the point: this workload no longer suits the host.
3. **Nothing can write.** `INDEX_DIR` is `BASE_DIR / "index"`, which on Lambda is
   the read-only `/var/task`, so SQLite and every index rebuild fail.

Lambda remains a good fit for the query-only service it was written for. Making
it fit the whole platform means routing the missing endpoints, moving state to
EFS or S3, and running the worker somewhere that persists — at which point a
container host is the simpler answer.
