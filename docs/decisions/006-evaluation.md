# ADR 006 — Evaluation Framework Design

**Status:** Accepted  
**Date:** 2026-07

---

## Context

Evaluating a RAG system requires measuring two orthogonal things: (1) whether retrieval
surfaces the right chunks, and (2) whether the generation produces faithful, accurate
answers.  Standard benchmarks conflate these; we need to measure both separately to
diagnose which component is failing.

## Decision

Separate the evaluation into two independent evaluators:

1. **`RetrievalEvaluator`** — pure retrieval metrics on ground-truth chunk IDs:
   Precision@K, Recall@K, Hit Rate, MRR.

2. **`GenerationEvaluator`** — LLM output quality:
   - Semantic similarity (cosine similarity between embedded answers)
   - Faithfulness (LLM-as-judge: is the answer grounded in the retrieved context?)

All metric functions are pure Python with no I/O — easily unit-tested without model
loading.

## Rationale

**Why separate evaluators?**  If overall accuracy drops, it could be due to poor
retrieval (wrong chunks) or poor generation (hallucination on good chunks).  Separate
metrics pinpoint the failure.

**Why Precision@K and MRR?**  Precision@K measures fraction of retrieved results that
are relevant (penalises noise).  MRR measures how highly the first relevant result is
ranked (penalises late retrieval).  Together they characterise both quality and ranking.

**Why cosine similarity for generation?**  Exact-match F1 fails on paraphrases.  ROUGE
requires very similar wording.  Cosine similarity between sentence embeddings captures
semantic equivalence across different phrasings — more robust for open-ended QA.

**Why LLM-as-judge for faithfulness?**  Hallucination is a binary signal that is hard
to measure with string metrics.  A judge model prompted with "does this answer stay
within the provided context?" detects fabricated claims that would score well on ROUGE.

## Consequences

- Ground-truth chunk IDs must be carefully constructed from real documents — fabricated
  IDs break the benchmark silently.
- LLM-as-judge requires a separate API call per sample (and a GROQ_API_KEY).  The system
  degrades gracefully: faithfulness is skipped when no judge is configured.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| RAGAS library | External dependency; less transparent metric computation |
| ROUGE / BLEU | Inadequate for semantic paraphrase matching |
| Human evaluation | Not automatable; not reproducible |
| Conflated end-to-end accuracy | Cannot diagnose retrieval vs generation failures |
