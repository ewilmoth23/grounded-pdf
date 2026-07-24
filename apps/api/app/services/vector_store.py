from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.exceptions import VectorStoreError


@dataclass(frozen=True)
class VectorRecord:
    id: str
    text: str
    embedding: list[float]
    metadata: dict[str, str | int]


@dataclass(frozen=True)
class VectorMatch:
    id: str
    text: str
    metadata: dict[str, Any]
    score: float


class VectorStore(Protocol):
    def upsert(self, records: list[VectorRecord]) -> None: ...

    def query(
        self, embedding: list[float], document_ids: list[str], limit: int
    ) -> list[VectorMatch]: ...

    def delete_document(self, document_id: str) -> None: ...

    def health(self) -> tuple[bool, str | None]: ...


class ChromaVectorStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._client: object | None = None
        self._collection: object | None = None
        self._lock = threading.Lock()

    def _get_collection(self) -> object:
        try:
            with self._lock:
                if self._collection is None:
                    import chromadb

                    self._client = chromadb.PersistentClient(path=str(self.path))
                    self._collection = self._client.get_or_create_collection(
                        "groundedpdf_chunks", metadata={"hnsw:space": "cosine"}
                    )
                return self._collection
        except Exception as exc:
            raise VectorStoreError("The local vector store is unavailable") from exc

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        try:
            collection = self._get_collection()
            collection.upsert(  # type: ignore[attr-defined]
                ids=[record.id for record in records],
                documents=[record.text for record in records],
                embeddings=[record.embedding for record in records],
                metadatas=[record.metadata for record in records],
            )
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Failed to store document embeddings") from exc

    def query(
        self, embedding: list[float], document_ids: list[str], limit: int
    ) -> list[VectorMatch]:
        if not document_ids:
            return []
        where: dict[str, Any]
        if len(document_ids) == 1:
            where = {"document_id": document_ids[0]}
        else:
            where = {"document_id": {"$in": document_ids}}
        try:
            results = self._get_collection().query(  # type: ignore[attr-defined]
                query_embeddings=[embedding], n_results=limit, where=where
            )
            ids = (results.get("ids") or [[]])[0]
            documents = (results.get("documents") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            return [
                VectorMatch(
                    id=item_id,
                    text=text,
                    metadata=metadata,
                    score=max(-1.0, min(1.0, 1.0 - float(distance))),
                )
                for item_id, text, metadata, distance in zip(
                    ids, documents, metadatas, distances, strict=True
                )
            ]
        except Exception as exc:
            raise VectorStoreError("Failed to search document embeddings") from exc

    def delete_document(self, document_id: str) -> None:
        try:
            self._get_collection().delete(where={"document_id": document_id})  # type: ignore[attr-defined]
        except Exception as exc:
            raise VectorStoreError("Failed to remove document embeddings") from exc

    def health(self) -> tuple[bool, str | None]:
        try:
            self._get_collection().count()  # type: ignore[attr-defined]
            return True, None
        except VectorStoreError as exc:
            return False, str(exc)
        except Exception:
            return False, "The local vector store is unavailable"


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        self.records.update({record.id: record for record in records})

    def query(
        self, embedding: list[float], document_ids: list[str], limit: int
    ) -> list[VectorMatch]:
        matches: list[VectorMatch] = []
        for record in self.records.values():
            if record.metadata.get("document_id") not in document_ids:
                continue
            score = sum(a * b for a, b in zip(embedding, record.embedding, strict=True))
            if math.isnan(score):
                score = -1.0
            matches.append(VectorMatch(record.id, record.text, record.metadata, score))
        return sorted(matches, key=lambda match: match.score, reverse=True)[:limit]

    def delete_document(self, document_id: str) -> None:
        self.records = {
            key: value
            for key, value in self.records.items()
            if value.metadata.get("document_id") != document_id
        }

    def health(self) -> tuple[bool, str | None]:
        return True, None
