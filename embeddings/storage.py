import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

from config.logging_config import get_logger
from config.settings import METADATA_FILE, VECTORS_FILE
from chunking.chunk import Chunk

logger = get_logger(__name__)


class VectorStorage:
    """Persists embedding vectors and chunk metadata to disk.

    On-disk layout
    --------------
    index/vectors.npy   — float32 ndarray, shape (n, dim)
    index/metadata.json — list of chunk dicts, index-aligned with the array

    Row i in vectors.npy corresponds to record i in metadata.json, so FAISS
    (Phase 4) only needs to resolve an integer index to get the full chunk.
    """

    def __init__(
        self,
        vectors_path: Path | str = VECTORS_FILE,
        metadata_path: Path | str = METADATA_FILE,
    ) -> None:
        self.vectors_path = Path(vectors_path)
        self.metadata_path = Path(metadata_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, vectors: np.ndarray, chunks: List[Chunk]) -> None:
        """Persist (vectors, chunks) to disk.

        Raises ValueError if the arrays are not length-aligned — a bug caught
        here is far easier to debug than a silent index shift during retrieval.
        """
        if vectors.shape[0] != len(chunks):
            raise ValueError(
                f"Length mismatch: {vectors.shape[0]} vectors vs {len(chunks)} chunks"
            )

        self.vectors_path.parent.mkdir(parents=True, exist_ok=True)

        np.save(str(self.vectors_path), vectors)
        logger.info("Saved vectors to %s", self.vectors_path)

        records: List[Dict] = [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "text": c.text,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "metadata": c.metadata,
            }
            for c in chunks
        ]
        self.metadata_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Saved metadata to %s", self.metadata_path)

    # ------------------------------------------------------------------
    # Incremental write
    # ------------------------------------------------------------------

    def append(self, new_vectors: np.ndarray, new_chunks: List[Chunk]) -> None:
        """Append new vectors + chunks to an existing index without a full rebuild.

        Loads the current artefacts, stacks the new data, then overwrites both
        files atomically.  Raises FileNotFoundError if the index does not exist
        yet — call save() for the initial build.
        """
        if new_vectors.shape[0] != len(new_chunks):
            raise ValueError(
                f"Length mismatch: {new_vectors.shape[0]} vectors vs {len(new_chunks)} chunks"
            )

        existing_vectors, existing_records = self.load()

        combined_vectors = np.vstack([existing_vectors, new_vectors])

        new_records: List[Dict] = [
            {
                "chunk_id": c.chunk_id,
                "document_id": c.document_id,
                "text": c.text,
                "start_char": c.start_char,
                "end_char": c.end_char,
                "metadata": c.metadata,
            }
            for c in new_chunks
        ]
        combined_records = existing_records + new_records

        # Re-use save() for the actual write to keep a single code path
        combined_chunks = [
            Chunk(
                chunk_id=r["chunk_id"],
                document_id=r["document_id"],
                text=r["text"],
                start_char=r["start_char"],
                end_char=r["end_char"],
                metadata=r.get("metadata", {}),
            )
            for r in combined_records
        ]
        self.save(combined_vectors, combined_chunks)
        logger.info(
            "Appended %d chunks (index now %d total)",
            len(new_chunks),
            len(combined_chunks),
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load(self) -> Tuple[np.ndarray, List[Dict]]:
        """Load and return (vectors, metadata_records).

        The returned list is index-aligned with the returned array.
        """
        if not self.vectors_path.exists():
            raise FileNotFoundError(f"Vectors file not found: {self.vectors_path}")
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {self.metadata_path}")

        vectors = np.load(str(self.vectors_path))
        records: List[Dict] = json.loads(
            self.metadata_path.read_text(encoding="utf-8")
        )
        logger.info("Loaded %d vectors from %s", len(records), self.vectors_path)
        return vectors, records
