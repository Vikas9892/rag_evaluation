"""Corpus namespacing.

A corpus is one indexed collection with its own FAISS index, BM25 store and
metadata. Retrieval is always scoped to exactly one, so an uploaded document
cannot leak into the evaluation corpus and change a benchmark result.

This is not multi-tenancy. There is no authentication, and anyone who can reach
the API can name any corpus. It is isolation between *collections*, which is
what this application actually needs: the evaluation corpus stays reproducible
while people upload their own documents beside it.
"""

from .index_manager import RemovalResult, chunk_count, remove_document
from .layout import (
    DEFAULT_CORPUS_ID,
    CorpusLayout,
    CorpusNotFoundError,
    InvalidCorpusIdError,
    corpus_layout,
    is_valid_corpus_id,
    list_corpus_ids,
)

__all__ = [
    "RemovalResult",
    "chunk_count",
    "remove_document",
    "DEFAULT_CORPUS_ID",
    "CorpusLayout",
    "CorpusNotFoundError",
    "InvalidCorpusIdError",
    "corpus_layout",
    "is_valid_corpus_id",
    "list_corpus_ids",
]
