# ADR 001 — Document Parser Strategy

**Status:** Accepted  
**Date:** 2026-07

---

## Context

The system must ingest documents in multiple formats (.pdf, .txt, .md).  Each format
requires different extraction logic.  The choice of parser affects text fidelity,
performance, and how easily new formats can be added.

## Decision

Introduce a `BaseParser` abstract base class with a single `parse(path) -> Document`
method.  Register concrete implementations (`PyMuPDFParser`, `PlainTextParser`) in a
format-keyed registry so the loader dispatches by file extension without `if/elif` chains.

## Rationale

**Why PyMuPDF (not pypdf or pdfminer)?**  PyMuPDF (`fitz`) extracts text with layout
preservation via `page.get_text("text")`.  It is consistently faster and more accurate
on multi-column PDFs than pypdf (pure-Python, struggles with complex layouts) or
pdfminer (accurate but ~3× slower and a larger dependency).

**Why a registry instead of hard-coded dispatch?**  Adding a new format (e.g. DOCX)
requires only: (1) create a subclass, (2) register one extension.  No existing code
changes.  This satisfies the Open/Closed Principle.

## Consequences

- Every new parser must implement `parse()` — a small contract with no hidden coupling.
- The `Document` dataclass is the single inter-module exchange format; parsers produce it,
  chunkers consume it.
- PDF text extraction quality depends on the PDF being machine-readable (not scanned).
  OCR (e.g. Tesseract) would be needed for scanned documents — out of scope for v1.

## Alternatives Considered

| Option | Rejected because |
|--------|-----------------|
| `pypdf` | Worse text extraction on complex layouts |
| `pdfminer.six` | ~3× slower, heavier dependency |
| LangChain document loaders | Unnecessary abstraction layer over PyMuPDF |
| Single function with `if ext == ".pdf"` | Violates Open/Closed; hard to test parsers in isolation |
