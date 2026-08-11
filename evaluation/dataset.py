import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from config.settings import DATASET_PATH

from .ground_truth import ChunkResolver, GroundTruthError


@dataclass
class BenchmarkSample:
    id: int
    question: str
    expected_answer: str
    expected_chunk_ids: List[str]


class DatasetLoader:
    """Loads and validates the evaluation benchmark from a JSON file.

    Ground truth is authored as content spans ("expected_answer_spans") and
    resolved to chunk IDs against the live index by an injected ChunkResolver.
    Positional IDs are not stored, because they silently re-point at different
    text whenever the corpus is re-chunked — see evaluation/ground_truth.py.

    A legacy "expected_chunk_ids" form is still accepted so that unit tests can
    construct fixtures without building an index.
    """

    @staticmethod
    def load(
        path: Path | str = DATASET_PATH,
        resolver: Optional[ChunkResolver] = None,
    ) -> List[BenchmarkSample]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")

        raw: list = json.loads(path.read_text(encoding="utf-8"))
        if not raw:
            raise ValueError(f"Dataset is empty: {path}")

        samples: List[BenchmarkSample] = []
        for entry in raw:
            samples.append(
                BenchmarkSample(
                    id=entry["id"],
                    question=entry["question"],
                    expected_answer=entry["expected_answer"],
                    expected_chunk_ids=DatasetLoader._ground_truth(entry, resolver),
                )
            )
        return samples

    @staticmethod
    def _ground_truth(entry: dict, resolver: Optional[ChunkResolver]) -> List[str]:
        """Resolve one entry's ground truth, preferring content spans."""
        spans = entry.get("expected_answer_spans")
        if spans is not None:
            if resolver is None:
                raise GroundTruthError(
                    f"Question {entry['id']} uses 'expected_answer_spans' but no "
                    "ChunkResolver was supplied. Pass "
                    "DatasetLoader.load(resolver=ChunkResolver.from_disk())."
                )
            try:
                return resolver.resolve_all(spans)
            except GroundTruthError as exc:
                raise GroundTruthError(f"Question {entry['id']}: {exc}") from exc

        if "expected_chunk_ids" in entry:
            return entry["expected_chunk_ids"]

        raise GroundTruthError(
            f"Question {entry['id']} declares no ground truth "
            "('expected_answer_spans' or legacy 'expected_chunk_ids')"
        )
