from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque

from app.core.config import Settings
from app.services.embeddings import EmbeddingProvider
from app.services.vector_store import VectorMatch, VectorStore

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
STOP_WORDS = {
    "and",
    "are",
    "did",
    "does",
    "for",
    "from",
    "how",
    "into",
    "its",
    "that",
    "the",
    "their",
    "this",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}
logger = logging.getLogger(__name__)


def _token_set(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 2}


def _content_tokens(text: str) -> set[str]:
    return _token_set(text) - STOP_WORDS


def _near_duplicate(left: str, right: str) -> bool:
    a, b = _token_set(left), _token_set(right)
    if not a or not b:
        return left.strip() == right.strip()
    return len(a & b) / len(a | b) >= 0.88


def deduplicate(matches: list[VectorMatch]) -> list[VectorMatch]:
    unique: list[VectorMatch] = []
    for match in matches:
        if any(_near_duplicate(match.text, item.text) for item in unique):
            continue
        unique.append(match)
    return unique


def diversify(matches: list[VectorMatch], limit: int) -> list[VectorMatch]:
    buckets: dict[str, deque[VectorMatch]] = defaultdict(deque)
    document_order: list[str] = []
    for match in matches:
        document_id = str(match.metadata["document_id"])
        if document_id not in buckets:
            document_order.append(document_id)
        buckets[document_id].append(match)
    selected: list[VectorMatch] = []
    while len(selected) < limit and any(buckets.values()):
        for document_id in document_order:
            if buckets[document_id] and len(selected) < limit:
                selected.append(buckets[document_id].popleft())
    return selected


class Retriever:
    def __init__(
        self, settings: Settings, embeddings: EmbeddingProvider, vector_store: VectorStore
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store

    def retrieve(self, question: str, document_ids: list[str]) -> list[VectorMatch]:
        started = time.monotonic()
        query_vector = self.embeddings.embed([question])[0]
        candidates = self.vector_store.query(
            query_vector, document_ids, self.settings.retrieval_count * 4
        )
        candidates = [
            candidate
            for candidate in candidates
            if candidate.score >= self.settings.retrieval_min_score
            and (
                bool(_content_tokens(question) & _content_tokens(candidate.text))
                or candidate.score >= self.settings.retrieval_semantic_confidence_score
            )
        ]
        results = diversify(deduplicate(candidates), self.settings.retrieval_count)
        logger.info(
            "retrieval_completed",
            extra={
                "duration_ms": round((time.monotonic() - started) * 1000),
                "count": len(results),
            },
        )
        return results
