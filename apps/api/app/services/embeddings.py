from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: object | None = None

    def _load(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        vectors = model.encode(  # type: ignore[attr-defined]
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [vector.tolist() for vector in vectors]


class DeterministicEmbeddingProvider:
    """Small hashing embedder used only by tests."""

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        output: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in TOKEN_RE.findall(text.lower()):
                digest = hashlib.sha256(token.encode()).digest()
                position = int.from_bytes(digest[:4], "big") % self.dimensions
                vector[position] += 1.0 if digest[4] % 2 else -1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            output.append([value / norm for value in vector])
        return output
