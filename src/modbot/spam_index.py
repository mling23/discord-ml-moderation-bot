"""In-memory index of known spam vectors.

All vectors are kept in a single numpy matrix so a similarity search against the
whole set is one vectorized matrix-vector product instead of a Python loop.
Vectors are expected to be L2-normalized (see :class:`~modbot.embedder.Embedder`),
which makes the dot product equal to cosine similarity.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MatchResult:
    similarity: float
    vector_id: int | None
    template_text: str


class SpamIndex:
    def __init__(
        self,
        vectors: Iterable[np.ndarray] | None = None,
        *,
        vector_ids: Iterable[int] | None = None,
        template_texts: Iterable[str] | None = None,
    ):
        self._matrix: np.ndarray | None = None
        self._vector_ids: list[int | None] = []
        self._template_texts: list[str] = []
        vectors = list(vectors) if vectors is not None else []
        if vectors:
            self._matrix = np.vstack(vectors).astype(np.float32)
            ids = list(vector_ids) if vector_ids is not None else []
            texts = list(template_texts) if template_texts is not None else []
            self._vector_ids = [ids[i] if i < len(ids) else None for i in range(len(vectors))]
            self._template_texts = [texts[i] if i < len(texts) else "" for i in range(len(vectors))]

    def __len__(self) -> int:
        return 0 if self._matrix is None else self._matrix.shape[0]

    def add(
        self,
        vector: np.ndarray,
        *,
        vector_id: int | None = None,
        template_text: str = "",
    ) -> None:
        row = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if self._matrix is None:
            self._matrix = row
        else:
            self._matrix = np.vstack([self._matrix, row])
        self._vector_ids.append(vector_id)
        self._template_texts.append(template_text)

    def max_similarity(self, vector: np.ndarray) -> float:
        """Return the highest cosine similarity between ``vector`` and the set."""
        if self._matrix is None:
            return 0.0
        similarities = self._matrix @ np.asarray(vector, dtype=np.float32)
        return float(similarities.max())

    def best_match(self, vector: np.ndarray) -> MatchResult:
        """Return the most similar known template and its metadata."""
        if self._matrix is None:
            return MatchResult(similarity=0.0, vector_id=None, template_text="")

        similarities = self._matrix @ np.asarray(vector, dtype=np.float32)
        best_idx = int(np.argmax(similarities))
        return MatchResult(
            similarity=float(similarities[best_idx]),
            vector_id=self._vector_ids[best_idx] if best_idx < len(self._vector_ids) else None,
            template_text=(
                self._template_texts[best_idx] if best_idx < len(self._template_texts) else ""
            ),
        )
