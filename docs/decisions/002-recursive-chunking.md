# ADR 002 — Recursive Character Chunking

**Status:** Accepted  
**Date:** 2026-07

---

## Context

Retrieval quality depends critically on chunk boundaries.  Chunks that are too large
dilute the relevance signal.  Chunks that are too small lose essential context.
Arbitrary character splits break sentences mid-word; naive sentence splitting fails
on technical text with abbreviations.

## Decision

Use LangChain's `RecursiveCharacterTextSplitter` with:
- `chunk_size = 500` characters
- `chunk_overlap = 100` characters
- `separators = ["\n\n", "\n", ". ", " ", ""]` (tried in order)

## Rationale

`RecursiveCharacterTextSplitter` tries each separator in order, falling back to the
next only when a split produces a chunk larger than `chunk_size`.  This preserves
paragraph structure first, then sentence structure, then word structure — giving the
most semantically coherent chunks possible within the size budget.

**Why 500 characters?**  BAAI/bge-small-en-v1.5 has a 512-token context limit.
500 characters ≈ 80–120 tokens for English text, leaving headroom for the query
during cross-attention and ensuring we never silently truncate a chunk.

**Why 100-character overlap?**  Prevents splitting a key sentence across adjacent
chunks.  100 characters ≈ 1–2 sentences; enough to maintain context continuity
without bloating the index.

## Consequences

- Chunk count grows sub-linearly with document length due to paragraph-preserving splits.
- Overlapping chunks mean some content is embedded twice — a deliberate trade-off for
  better retrieval at the cost of ~20% index inflation.
- Character-based chunking is language-agnostic; a token-aware splitter would be
  strictly better for multilingual content.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| Fixed character split (no separators) | Splits mid-sentence; poor retrieval quality |
| Sentence-aware NLTK tokenizer | Fails on technical abbreviations; slower |
| Semantic chunking (embedding similarity) | 10–50× slower; harder to control chunk size |
| Token-based splitter | Requires tokenizer per model family; complex |
