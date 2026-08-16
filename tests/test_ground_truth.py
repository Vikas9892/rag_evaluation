"""Tests for content-anchored ground truth resolution.

The final class is the regression guard for the failure that motivated this
module: labels anchored to positional chunk IDs silently re-pointed at
different text when the corpus was re-chunked, and nothing failed.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DATASET_PATH, METADATA_FILE
from evaluation.dataset import DatasetLoader
from evaluation.ground_truth import ChunkResolver, GroundTruthError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

RECORDS = [
    {"chunk_id": "doc_chunk_0000", "text": "# Title Only"},
    {
        "chunk_id": "doc_chunk_0001",
        "text": "Paging divides memory into\nfixed-size pages.",
    },
    {"chunk_id": "doc_chunk_0002", "text": "- FIFO\n- LRU (Least Recently Used)"},
]


@pytest.fixture
def resolver() -> ChunkResolver:
    return ChunkResolver(RECORDS)


# ---------------------------------------------------------------------------
# ChunkResolver.resolve
# ---------------------------------------------------------------------------


class TestResolve:
    def test_resolves_unique_span(self, resolver):
        assert resolver.resolve("LRU (Least Recently Used)") == "doc_chunk_0002"

    def test_normalises_whitespace_across_line_breaks(self, resolver):
        # The span is authored on one line; the chunk wraps it across two.
        assert (
            resolver.resolve("divides memory into fixed-size pages") == "doc_chunk_0001"
        )

    def test_tolerates_extra_whitespace_in_span(self, resolver):
        assert resolver.resolve("-  FIFO") == "doc_chunk_0002"

    def test_missing_span_raises(self, resolver):
        with pytest.raises(GroundTruthError, match="not found"):
            resolver.resolve("segmentation with TLB shootdown")

    def test_ambiguous_span_raises_and_names_matches(self, resolver):
        # "e" appears in every chunk.
        with pytest.raises(GroundTruthError, match="ambiguous"):
            resolver.resolve("e")

    def test_empty_span_raises(self, resolver):
        with pytest.raises(GroundTruthError, match="empty"):
            resolver.resolve("   ")

    def test_size_reports_chunk_count(self, resolver):
        assert resolver.size == 3


class TestResolveAll:
    def test_resolves_multiple_spans_to_multiple_chunks(self, resolver):
        ids = resolver.resolve_all(["fixed-size pages", "LRU (Least Recently Used)"])
        assert ids == ["doc_chunk_0001", "doc_chunk_0002"]

    def test_deduplicates_spans_landing_in_one_chunk(self, resolver):
        ids = resolver.resolve_all(["FIFO", "LRU (Least Recently Used)"])
        assert ids == ["doc_chunk_0002"]

    def test_preserves_order(self, resolver):
        ids = resolver.resolve_all(["LRU (Least Recently Used)", "fixed-size pages"])
        assert ids == ["doc_chunk_0002", "doc_chunk_0001"]

    def test_empty_span_list_raises(self, resolver):
        with pytest.raises(GroundTruthError, match="at least one span"):
            resolver.resolve_all([])

    def test_one_bad_span_fails_the_whole_entry(self, resolver):
        with pytest.raises(GroundTruthError):
            resolver.resolve_all(["FIFO", "nonexistent text"])


class TestFromDisk:
    def test_missing_metadata_raises_actionable_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Build the index"):
            ChunkResolver.from_disk(tmp_path / "absent.json")

    def test_loads_real_index(self):
        r = ChunkResolver.from_disk()
        assert r.size > 0


# ---------------------------------------------------------------------------
# DatasetLoader integration
# ---------------------------------------------------------------------------


class TestDatasetLoaderResolution:
    def _write(self, tmp_path, entries) -> Path:
        p = tmp_path / "ds.json"
        p.write_text(json.dumps(entries), encoding="utf-8")
        return p

    def test_resolves_spans_into_chunk_ids(self, tmp_path, resolver):
        p = self._write(
            tmp_path,
            [
                {
                    "id": 1,
                    "question": "Q?",
                    "expected_answer": "A.",
                    "expected_answer_spans": ["LRU (Least Recently Used)"],
                }
            ],
        )
        samples = DatasetLoader.load(p, resolver=resolver)
        assert samples[0].expected_chunk_ids == ["doc_chunk_0002"]

    def test_spans_without_resolver_raise(self, tmp_path):
        p = self._write(
            tmp_path,
            [
                {
                    "id": 7,
                    "question": "Q?",
                    "expected_answer": "A.",
                    "expected_answer_spans": ["FIFO"],
                }
            ],
        )
        with pytest.raises(GroundTruthError, match="no ChunkResolver"):
            DatasetLoader.load(p)

    def test_error_names_the_offending_question(self, tmp_path, resolver):
        p = self._write(
            tmp_path,
            [
                {
                    "id": 42,
                    "question": "Q?",
                    "expected_answer": "A.",
                    "expected_answer_spans": ["text that does not exist"],
                }
            ],
        )
        with pytest.raises(GroundTruthError, match="Question 42"):
            DatasetLoader.load(p, resolver=resolver)

    def test_legacy_chunk_ids_still_load(self, tmp_path):
        """Fixtures may use literal IDs so unit tests need no index."""
        p = self._write(
            tmp_path,
            [
                {
                    "id": 1,
                    "question": "Q?",
                    "expected_answer": "A.",
                    "expected_chunk_ids": ["c1"],
                }
            ],
        )
        assert DatasetLoader.load(p)[0].expected_chunk_ids == ["c1"]

    def test_entry_with_no_ground_truth_raises(self, tmp_path):
        p = self._write(
            tmp_path, [{"id": 3, "question": "Q?", "expected_answer": "A."}]
        )
        with pytest.raises(GroundTruthError, match="declares no ground truth"):
            DatasetLoader.load(p)


# ---------------------------------------------------------------------------
# CI invariant — the regression guard
# ---------------------------------------------------------------------------


class TestShippedDatasetIntegrity:
    """Every label in the real dataset must resolve against the real index.

    This is the test that would have caught the 2026-08-11 incident, where
    changing CHUNK_SIZE 500 -> 250 left every positional label pointing at the
    wrong text while the entire suite stayed green.
    """

    def test_every_span_resolves_to_exactly_one_chunk(self):
        DatasetLoader.load(DATASET_PATH, resolver=ChunkResolver.from_disk())

    def test_dataset_uses_content_anchors_not_positional_ids(self):
        entries = json.loads(Path(DATASET_PATH).read_text(encoding="utf-8"))
        offenders = [e["id"] for e in entries if "expected_chunk_ids" in e]
        assert not offenders, (
            f"Questions {offenders} still use positional chunk IDs. "
            "Positional labels silently re-point when the corpus is re-chunked; "
            "use 'expected_answer_spans' instead."
        )

    def test_every_question_has_ground_truth(self):
        samples = DatasetLoader.load(DATASET_PATH, resolver=ChunkResolver.from_disk())
        assert all(s.expected_chunk_ids for s in samples)

    def test_resolved_ids_exist_in_the_index(self):
        index_ids = {
            r["chunk_id"]
            for r in json.loads(Path(METADATA_FILE).read_text(encoding="utf-8"))
        }
        samples = DatasetLoader.load(DATASET_PATH, resolver=ChunkResolver.from_disk())
        for s in samples:
            for cid in s.expected_chunk_ids:
                assert (
                    cid in index_ids
                ), f"Question {s.id} resolved to unknown chunk {cid}"
