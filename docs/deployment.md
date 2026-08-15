# Deployment

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
