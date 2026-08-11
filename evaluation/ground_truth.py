"""Content-anchored ground truth resolution.

Why this module exists
----------------------
Ground truth used to be stored as positional chunk IDs::

    {"id": 13, "expected_chunk_ids": ["os.md_chunk_0001"]}

A chunk ID is a function of chunk size, overlap, and separators.  Re-chunking
the corpus therefore silently re-points every label at different content: the
ID still resolves, no error is raised, and the metrics quietly become wrong.
Observed on 2026-08-11 — changing CHUNK_SIZE 500 -> 250 moved MRR from 1.000 to
0.143 with no failure anywhere in the pipeline or the test suite.

The fix is to anchor labels to *content* and resolve them to chunk IDs against
the live index at evaluation time::

    {"id": 13, "expected_answer_spans": ["- LRU (Least Recently Used)"]}

Re-chunk however you like; the label still points at the text that answers the
question, or the resolver fails loudly.

Resolution contract
-------------------
Each span must match **exactly one** chunk.

- zero matches  -> the span no longer exists in the corpus (label is stale)
- 2+ matches    -> the span is not discriminative (label is ambiguous)

Both are label bugs, and both raise.  A question may carry several spans when
its answer genuinely spans multiple chunks (the OSI layer table, for example);
the relevant set is then the union of the resolved IDs.

Matching is whitespace-normalised so that labels survive re-flowing, changed
line breaks, and separator tweaks — the failure mode this module exists to
prevent must not be reintroduced by brittle string comparison.
"""
import json
from pathlib import Path
from typing import Dict, List, Sequence

from config.logging_config import get_logger
from config.settings import METADATA_FILE

logger = get_logger(__name__)


class GroundTruthError(ValueError):
    """Raised when a ground-truth span does not resolve to exactly one chunk."""


def _normalise(text: str) -> str:
    """Collapse all whitespace runs to single spaces for tolerant matching."""
    return " ".join(text.split())


class ChunkResolver:
    """Resolves content spans to chunk IDs against a specific index.

    Constructed from index metadata, so the resolver always reflects the corpus
    as it is *now* rather than as it was when the labels were written.
    """

    def __init__(self, records: Sequence[dict]) -> None:
        self._by_id: Dict[str, str] = {
            r["chunk_id"]: _normalise(r["text"]) for r in records
        }

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_disk(cls, metadata_path: Path | str = METADATA_FILE) -> "ChunkResolver":
        path = Path(metadata_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Index metadata not found: {path}. "
                "Build the index before running evaluation."
            )
        records = json.loads(path.read_text(encoding="utf-8"))
        logger.info("ChunkResolver ready: %d chunks", len(records))
        return cls(records)

    # ------------------------------------------------------------------
    # Core operation
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return len(self._by_id)

    def resolve(self, span: str) -> str:
        """Return the ID of the single chunk containing span.

        Raises GroundTruthError on zero or multiple matches — a label that
        matches nothing is stale, and one that matches several is ambiguous.
        """
        needle = _normalise(span)
        if not needle:
            raise GroundTruthError("Ground-truth span is empty")

        matches = [cid for cid, text in self._by_id.items() if needle in text]

        if not matches:
            raise GroundTruthError(
                f"Span not found in any chunk: {span!r}. "
                "The corpus or chunking changed — re-anchor this label."
            )
        if len(matches) > 1:
            raise GroundTruthError(
                f"Span is ambiguous, matched {len(matches)} chunks "
                f"({', '.join(sorted(matches))}): {span!r}. "
                "Extend the span until it identifies exactly one chunk."
            )
        return matches[0]

    def resolve_all(self, spans: Sequence[str]) -> List[str]:
        """Resolve every span, de-duplicated, order preserved.

        Two spans may legitimately land in the same chunk; the relevant set is
        a set, so duplicates collapse.
        """
        if not spans:
            raise GroundTruthError("A ground-truth entry must declare at least one span")

        resolved: List[str] = []
        for span in spans:
            cid = self.resolve(span)
            if cid not in resolved:
                resolved.append(cid)
        return resolved
