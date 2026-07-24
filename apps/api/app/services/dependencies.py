from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.rag.verification import clear_verification_cache
from app.services.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from app.services.vector_store import ChromaVectorStore, InMemoryVectorStore, VectorStore


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.environment == "test" or settings.model_provider == "mock":
        return DeterministicEmbeddingProvider()
    return SentenceTransformerEmbeddingProvider(settings.embedding_model)


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.environment == "test":
        return InMemoryVectorStore()
    return ChromaVectorStore(settings.chroma_dir)


def clear_service_caches() -> None:
    get_embedding_provider.cache_clear()
    get_vector_store.cache_clear()
    clear_verification_cache()
