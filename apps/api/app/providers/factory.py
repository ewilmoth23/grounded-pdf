"""Chat provider construction.

Providers hold a lazily created shared ``httpx.AsyncClient``, so instances are
cached here per relevant settings values and reused across requests instead of
being rebuilt (and re-pooled) on every call. The cache is a small LRU so
repeated runtime settings changes cannot accumulate unbounded pooled clients.
``aclose_chat_providers`` closes the shared clients on application shutdown;
``clear_chat_provider_cache`` drops cached instances without closing (used for
test isolation, where the clients are never opened against real connections).
"""

from __future__ import annotations

from collections import OrderedDict

from app.core.config import Settings
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import ChatProvider
from app.providers.mock import MockChatProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

_CacheKey = tuple[str | None, ...]
_PROVIDER_CACHE_LIMIT = 4
_provider_cache: OrderedDict[_CacheKey, ChatProvider] = OrderedDict()
# Providers evicted from the LRU may still be serving in-flight requests, and
# eviction happens in synchronous request code where an async ``aclose`` cannot
# be awaited (and fire-and-forget tasks could race those requests). Evicted
# instances are parked here and closed alongside the cache by
# ``aclose_chat_providers`` on application shutdown.
_evicted_providers: list[ChatProvider] = []


def _cache_key(settings: Settings) -> _CacheKey:
    """Every settings value a provider reads; a change yields a fresh instance."""
    return (
        settings.environment,
        settings.model_provider,
        settings.model_name,
        settings.ollama_base_url,
        settings.openai_base_url,
        settings.openai_api_key,
        str(settings.temperature),
        str(settings.max_output_tokens),
        str(settings.model_timeout_seconds),
    )


def create_chat_provider(settings: Settings) -> ChatProvider:
    key = _cache_key(settings)
    cached = _provider_cache.get(key)
    if cached is not None:
        _provider_cache.move_to_end(key)
        return cached
    provider: ChatProvider
    if settings.model_provider == "ollama":
        provider = OllamaProvider(settings)
    elif settings.model_provider == "openai_compatible":
        provider = OpenAICompatibleProvider(settings)
    elif settings.model_provider == "mock" and settings.environment == "test":
        provider = MockChatProvider()
    else:
        raise ProviderUnavailableError("The configured model provider is not available")
    _provider_cache[key] = provider
    while len(_provider_cache) > _PROVIDER_CACHE_LIMIT:
        _, evicted = _provider_cache.popitem(last=False)
        _evicted_providers.append(evicted)
    return provider


def clear_chat_provider_cache() -> None:
    _provider_cache.clear()
    _evicted_providers.clear()


async def aclose_chat_providers() -> None:
    """Close every cached or evicted provider's shared HTTP client (app shutdown)."""
    providers = [*_provider_cache.values(), *_evicted_providers]
    _provider_cache.clear()
    _evicted_providers.clear()
    for provider in providers:
        aclose = getattr(provider, "aclose", None)
        if aclose is not None:
            await aclose()
