from __future__ import annotations

from qdrant_client import models


def normalize_lexical_weights(weights: dict[str | int, float]) -> dict[int, float]:
    normalized = {
        int(token_id): float(weight)
        for token_id, weight in weights.items()
        if float(weight) != 0.0
    }
    return dict(sorted(normalized.items()))


def to_sparse_vector(weights: dict[int, float]) -> models.SparseVector:
    ordered = sorted(weights.items())
    return models.SparseVector(
        indices=[token_id for token_id, _ in ordered],
        values=[weight for _, weight in ordered],
    )
