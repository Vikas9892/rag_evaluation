# ADR 002 — Recursive Character Chunking

**Status:** Accepted — parameters amended 2026-08 (see [Amendment](#amendment-2026-08))
**Date:** 2026-07

---

> **The numbers below are the original decision, kept as written.** The shipped
> configuration is now `chunk_size = 250`, `chunk_overlap = 50`, with heading
> separators prepended and a minimum-chunk merge. The amendment at the end of
> this file records what changed and why.

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

---

## Amendment (2026-08)

Shipped in `9e908da`, then refined when the sub-threshold merge landed.

| Parameter | Original | Now |
|---|---|---|
| `chunk_size` | 500 | **250** |
| `chunk_overlap` | 100 | **50** |
| `separators` | `["\n\n", "\n", ". ", " ", ""]` | **`"\n## "` and `"\n### "` prepended** |
| minimum chunk | — | **`MIN_CHUNK_CHARS = 50`**, clamped to `chunk_size // 2` |

**What went wrong with 500.** Paragraph-first splitting produced chunks spanning
several sections. `os.md` came out as two ~485-character chunks, and the first
of them ranked first for *every* query about that document — a grab-bag matches
everything and answers nothing. Rank-1 results before → after:

| Query | Before | After |
|---|---|---|
| "LRU page replacement" | `os.md#1` (grab-bag) | `os.md#4` (Page Replacement) |
| "dining philosophers problem" | `dbms.md#2` (wrong document) | `os.md#6` (Synchronisation) |
| "what does an inode store" | `os.md#1` (grab-bag) | `os.md#5` (File Systems) |

**Why headings first.** Splitting on `\n## ` before `\n\n` keeps one chunk to one
concept, which is the property the retrieval signal actually depends on. The
original rationale for 500 characters — staying inside bge-small's 512-token
window — still holds at 250; it was never the binding constraint.

**Why a minimum.** Heading-aware splitting emits heading-only chunks such as
`## ACID Properties`. Indexed alone they are pure noise: they match a query's
phrasing closely while containing none of the answer, so they outrank the chunk
that holds it. Short chunks now merge *forward*, making the heading a prefix of
the section it introduces, so the heading survives as signal rather than being
dropped.

**Cost.** The corpus inflates — `os.md` went from 2 chunks to 7 — which is the
~20% index inflation the original trade-off anticipated, only larger. At this
corpus size that is not a constraint worth optimising against.

Chunking remains an **indexing-time** decision: changing any of it requires
re-embedding and rebuilding the index, so it is not exposed as a query
parameter. See `chunking/config.py`.
