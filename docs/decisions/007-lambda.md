# ADR 007 — Deployment Target (AWS Lambda + Mangum)

**Status:** Accepted  
**Date:** 2026-07

---

## Context

The RAG API must be deployable without managing a persistent server, must scale to zero
when idle, and must minimise operational overhead.  The API handles bursty, low-to-
medium throughput workloads (< 100 req/s at peak).

## Decision

Deploy the FastAPI app on AWS Lambda via the Mangum ASGI adapter, with AWS API Gateway
(HTTP API) as the entry point.  Use AWS SAM for infrastructure-as-code.

## Rationale

**Why Lambda over ECS/EC2/Fargate?**
- Scale-to-zero: no cost when idle.
- No capacity planning: Lambda handles bursting automatically.
- Operational simplicity: no AMI management, no ECS task definitions, no autoscaling
  policies.

**Why Mangum?**  Mangum translates Lambda's event/context interface into ASGI scope,
receive, and send — letting FastAPI run completely unmodified.  The translation adds
< 1 ms of overhead.

**Why HTTP API over REST API?**  HTTP API is lower latency (~10 ms less per request),
lower cost (70% cheaper per million requests), and sufficient for our use case.  REST
API adds features like API keys, usage plans, and WAF integration that we don't need.

**Why FastAPI over Flask/Django?**  FastAPI is async-native (non-blocking I/O for LLM
calls), generates OpenAPI docs automatically, and uses Pydantic for request validation.
The dependency-injection system (`Depends`) makes testing clean.

**Cold start mitigation:**  The sentence-transformer model (~130 MB) causes ~4–8 s cold
starts.  Mitigation strategies: (1) Lambda SnapStart (for Java, not yet Python), (2)
store model weights in a Lambda Layer or S3 and cache in /tmp, (3) provision 1–2
concurrency to keep a warm container alive.

## Consequences

- Lambda has a 250 MB unzipped package limit.  FAISS index + model weights exceed this
  — they must be stored in S3 and loaded into `/tmp` at cold start.
- 60-second timeout covers even slow Groq API responses with retries.
- 1024 MB memory is sufficient for the BGE-small model + FAISS index.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| ECS Fargate | Persistent cost even at zero traffic; more operational overhead |
| EC2 | Manual capacity management; over-provisioned for bursty workloads |
| Kubernetes | Major operational overhead for a single-service API |
| Google Cloud Run | Vendor preference for AWS; functionally equivalent |
| Render / Railway | Less enterprise-credible; fewer IAM / VPC controls |
