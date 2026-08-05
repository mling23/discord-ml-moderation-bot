"""Thin wrapper around a sentence-transformers model.

Encoding text is CPU-bound and blocks for tens of milliseconds. Running it
directly inside an ``async`` handler would freeze the whole bot, so we offload
it to a thread via ``run_in_executor``. Vectors are L2-normalized on the way out
so that cosine similarity later reduces to a simple dot product.
"""

import asyncio

import numpy as np
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str):
        self._model = SentenceTransformer(model_name)

    async def encode(self, text: str) -> np.ndarray:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._encode_sync, text)

    def _encode_sync(self, text: str) -> np.ndarray:
        vector = np.asarray(self._model.encode(text), dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm
