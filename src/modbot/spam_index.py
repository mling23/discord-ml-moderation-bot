"""In-memory index of known spam vectors.

All vectors are kept in a single numpy matrix so a similarity search against the
whole set is one vectorized matrix-vector product instead of a Python loop.
Vectors are expected to be L2-normalized (see :class:`~modbot.embedder.Embedder`),
which makes the dot product equal to cosine similarity.
"""

from collections.abc import Iterable

import numpy as np


class SpamIndex:
    def __init__(self, vectors: Iterable[np.ndarray] | None = None):
        self._matrix: np.ndarray | None = None
        vectors = list(vectors) if vectors is not None else []
        if vectors:
            self._matrix = np.vstack(vectors).astype(np.float32)

    def __len__(self) -> int:
        return 0 if self._matrix is None else self._matrix.shape[0]

    def add(self, vector: np.ndarray) -> None:
        row = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if self._matrix is None:
            self._matrix = row
        else:
            self._matrix = np.vstack([self._matrix, row])

    def max_similarity(self, vector: np.ndarray) -> float:
        """Return the highest cosine similarity between ``vector`` and the set."""
        if self._matrix is None:
            return 0.0
        similarities = self._matrix @ np.asarray(vector, dtype=np.float32)
        return float(similarities.max())
