"""Pure metric functions — no I/O, no side effects, trivially testable."""
from typing import List

import numpy as np


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """Fraction of the top-k retrieved items that are relevant.

    Precision@k = |retrieved[:k] ∩ relevant| / k
    """
    if k <= 0:
        return 0.0
    relevant_set = set(relevant_ids)
    hits = sum(1 for rid in retrieved_ids[:k] if rid in relevant_set)
    return hits / k


def recall_at_k(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """Fraction of all relevant items that appear in the retrieved list.

    Recall = |retrieved ∩ relevant| / |relevant|
    Returns 1.0 when relevant_ids is empty (nothing to miss).
    """
    if not relevant_ids:
        return 1.0
    relevant_set = set(relevant_ids)
    retrieved_set = set(retrieved_ids)
    return len(retrieved_set & relevant_set) / len(relevant_set)


def hit_rate(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """1.0 if at least one relevant item was retrieved, else 0.0."""
    relevant_set = set(relevant_ids)
    return 1.0 if any(rid in relevant_set for rid in retrieved_ids) else 0.0


def reciprocal_rank(retrieved_ids: List[str], relevant_ids: List[str]) -> float:
    """1 / rank of the first relevant item (0.0 if none found).

    Rank is 1-indexed.
    """
    relevant_set = set(relevant_ids)
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_set:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(rrs: List[float]) -> float:
    """Average of per-query reciprocal ranks."""
    return float(np.mean(rrs)) if rrs else 0.0


# ---------------------------------------------------------------------------
# Similarity metric
# ---------------------------------------------------------------------------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two 1-D float arrays, in [-1, 1].

    Returns 0.0 if either vector is the zero vector.
    """
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
