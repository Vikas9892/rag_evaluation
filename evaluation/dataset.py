import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config.settings import DATASET_PATH


@dataclass
class BenchmarkSample:
    id: int
    question: str
    expected_answer: str
    expected_chunk_ids: List[str]


class DatasetLoader:
    """Loads and validates the evaluation benchmark from a JSON file."""

    @staticmethod
    def load(path: Path | str = DATASET_PATH) -> List[BenchmarkSample]:
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
                    expected_chunk_ids=entry["expected_chunk_ids"],
                )
            )
        return samples
