# ADR 005 — Provider Abstraction (BaseGenerator, BaseParser, BaseReranker)

**Status:** Accepted  
**Date:** 2026-07

---

## Context

LLM providers (Groq, OpenAI, Anthropic) have different Python SDKs and streaming
interfaces.  Document formats (.pdf, .txt, .md) require different parsers.  Re-rankers
have different model families.  Coupling the pipeline to any single provider makes
switching providers a large refactor.

## Decision

Define abstract base classes (`BaseGenerator`, `BaseParser`, `BaseReranker`) with a
single abstract method each.  Concrete implementations subclass and override that method.
The pipeline code depends only on the abstract interface, never on a concrete class.

## Rationale

This is the Dependency Inversion Principle applied at the Python class level.

**`BaseGenerator.generate(prompt, sources) → GenerationResponse`** is the only contract.
`GroqGenerator` implements it with exponential-backoff retries.  A future
`OpenAIGenerator` or `AnthropicGenerator` needs zero changes to the retrieval,
evaluation, or API layers.

**`BaseParser.parse(path) → Document`** is registered per-extension.  `PyMuPDFParser`
handles PDFs; `PlainTextParser` handles `.txt` / `.md`.  A DOCX parser is one class.

**`BaseReranker.rerank(query, results, top_k)`** keeps cross-encoder logic isolated from
the retriever.  Any re-ranking model (BM25-based, pointwise, listwise) slots in.

**Test doubles:**  Abstract interfaces make mocking trivial — `MockGenerator`,
`MockEmbedder`, `MockRetriever` are 5-line classes that fulfil the contract.  This
keeps 90%+ of tests fast and offline.

## Consequences

- A new provider requires: (1) subclass, (2) implement one method, (3) register or
  inject.  Existing code is untouched.
- Abstract base classes add a small amount of boilerplate.  The trade-off is worth it
  for a system that is explicitly designed to evaluate multiple configurations.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| Single function `generate(provider, prompt)` with `if/elif` | Open/Closed violation; untestable without all providers |
| LangChain / LlamaIndex abstractions | Heavy frameworks; many unnecessary dependencies |
| Protocol classes (structural subtyping) | Less explicit; no enforcement on missing methods |
