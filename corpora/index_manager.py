"""Maintaining a corpus's index after it has been built.

Removing a document is the operation that matters here. FAISS `IndexFlatIP` has
no delete, which is why the first cut of `DELETE /documents/{id}` could only
report that chunks stayed searchable. That was honest but unsatisfying: the
vectors are already on disk, so a rebuild costs no embedding — it is a filter
over a NumPy array and a re-add.

The expensive part of indexing is the embedding model, and this never touches
it.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from config.logging_config import get_logger
from corpora.layout import CorpusLayout, corpus_layout

logger = get_logger(__name__)


@dataclass(frozen=True)
class RemovalResult:
    """What a removal actually did, so the API can say so rather than guess."""

    removed_chunks: int
    remaining_chunks: int
    corpus_deleted: bool


def _document_id_of(record: dict) -> Optional[str]:
    """The upload's id, which lives in the chunk's own metadata.

    The record's top-level `document_id` is the *filename* — it is what a
    citation shows — and two uploads can share one. The generated id is what
    identifies the upload, so removal matches on that.
    """
    metadata = record.get("metadata") or {}
    return metadata.get("document_id")


def remove_document(corpus_id: str, document_id: str) -> RemovalResult:
    """Drop one document's chunks from a corpus and rebuild its index.

    Rebuilding rather than tombstoning: a tombstone would keep the vector in the
    FAISS search, so a deleted document would still consume a top-K slot and
    have to be filtered out afterwards — which silently shortens every result
    list. Rebuilding leaves an index that means what it says.
    """
    # Imported here, not at module scope: retrieval imports corpora, so a
    # top-level import would close the cycle and break both packages.
    from retrieval.faiss_store import FAISSStore

    layout = corpus_layout(corpus_id)
    if not layout.exists:
        return RemovalResult(0, 0, corpus_deleted=False)

    records: List[dict] = json.loads(layout.metadata_path.read_text(encoding="utf-8"))
    vectors = np.load(layout.vectors_path)

    if len(records) != vectors.shape[0]:
        # The two files are index-aligned by construction. If they are not, a
        # filter would pair the wrong vector with the wrong chunk, so refuse.
        raise ValueError(
            f"Corpus {corpus_id!r} is inconsistent: {len(records)} records but "
            f"{vectors.shape[0]} vectors. Rebuild it before removing documents."
        )

    keep = [i for i, r in enumerate(records) if _document_id_of(r) != document_id]
    removed = len(records) - len(keep)
    if removed == 0:
        return RemovalResult(0, len(records), corpus_deleted=False)

    if not keep:
        # Nothing left. An empty index is not queryable, and leaving one behind
        # would advertise a corpus with no content.
        _delete_corpus_files(layout)
        logger.info("Removed the last document from corpus %s; corpus deleted", corpus_id)
        return RemovalResult(removed, 0, corpus_deleted=True)

    kept_records = [records[i] for i in keep]
    kept_vectors = vectors[keep]

    np.save(str(layout.vectors_path), kept_vectors)
    layout.metadata_path.write_text(
        json.dumps(kept_records, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    store = FAISSStore(dimension=kept_vectors.shape[1])
    store.add(kept_vectors)
    store.save(layout.faiss_path)

    logger.info(
        "Removed %d chunk(s) for document %s from corpus %s; %d remain",
        removed,
        document_id,
        corpus_id,
        len(kept_records),
    )
    return RemovalResult(removed, len(kept_records), corpus_deleted=False)


def _delete_corpus_files(layout: CorpusLayout) -> None:
    for path in (layout.vectors_path, layout.metadata_path, layout.faiss_path):
        Path(path).unlink(missing_ok=True)
    # Only the directory this corpus owns, and only if empty — the default
    # corpus shares its directory with the offline pipeline's artefacts.
    if not layout.is_default and layout.root.is_dir():
        try:
            layout.root.rmdir()
        except OSError:
            logger.debug("Corpus directory %s not empty; left in place", layout.root)


def chunk_count(corpus_id: str) -> int:
    """Chunks currently indexed, read from the index rather than from records."""
    layout = corpus_layout(corpus_id)
    if not layout.exists:
        return 0
    return len(json.loads(layout.metadata_path.read_text(encoding="utf-8")))
