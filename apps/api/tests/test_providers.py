import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ProviderUnavailableError
from app.providers import factory
from app.providers.factory import (
    aclose_chat_providers,
    clear_chat_provider_cache,
    create_chat_provider,
)
from app.providers.mock import MockChatProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.rag.chat import ChatService


class UnavailableProvider:
    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        del system_prompt, user_prompt
        if False:
            yield ""
        raise ProviderUnavailableError("Provider unavailable for test")

    async def health(self) -> tuple[bool, str | None]:
        return False, "Provider unavailable for test"


class UnusedRetriever:
    pass


@pytest.mark.asyncio
async def test_provider_cache_is_bounded_and_evictions_are_closed() -> None:
    clear_chat_provider_cache()
    try:
        providers = [
            create_chat_provider(Settings(model_provider="ollama", model_name=f"model-{index}"))
            for index in range(6)
        ]
        assert len(factory._provider_cache) == 4
        # The two oldest providers were evicted but parked for shutdown closing.
        assert factory._evicted_providers == providers[:2]
        # A cached configuration returns the same instance.
        assert (
            create_chat_provider(Settings(model_provider="ollama", model_name="model-5"))
            is providers[5]
        )
        await aclose_chat_providers()
        assert not factory._provider_cache
        assert not factory._evicted_providers
    finally:
        clear_chat_provider_cache()


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic() -> None:
    provider = MockChatProvider()
    tokens = [
        token
        async for token in provider.stream(
            "system", "CONTEXT\nSOURCE [sample.pdf, p. 2]\n37 percent\nQUESTION\nHow much?"
        )
    ]
    answer = "".join(tokens)
    assert "37 percent" in answer
    assert "[sample.pdf, p. 2]" in answer


@pytest.mark.asyncio
async def test_unavailable_ollama_health_is_reported() -> None:
    provider = OllamaProvider(Settings(ollama_base_url="http://127.0.0.1:1"))
    healthy, detail = await provider.health()
    assert healthy is False
    assert detail == "Ollama is not reachable"


@pytest.mark.asyncio
async def test_ollama_health_requires_the_configured_model() -> None:
    settings = Settings(model_name="local-model", ollama_base_url="http://ollama.test")
    missing = OllamaProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"models": [{"name": "other:latest"}]})
        ),
    )
    assert await missing.health() == (
        False,
        "Configured Ollama model is not installed (local-model)",
    )

    available = OllamaProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"models": [{"name": "local-model:latest"}]})
        ),
    )
    assert await available.health() == (True, None)


@pytest.mark.asyncio
async def test_unavailable_ollama_stream_is_reported() -> None:
    provider = OllamaProvider(
        Settings(environment="test", model_provider="ollama", ollama_base_url="http://127.0.0.1:1")
    )
    with pytest.raises(ProviderUnavailableError, match="Ollama is unavailable"):
        _ = [token async for token in provider.stream("system", "question")]


@pytest.mark.asyncio
async def test_ollama_streams_tokens_and_reports_declared_errors() -> None:
    def success(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert payload["model"] == "local-model"
        return httpx.Response(
            200,
            content=(
                b'{"message":{"content":"Grounded "}}\n'
                b'{"message":{"content":"answer"},"done":true}\n'
            ),
        )

    settings = Settings(
        environment="test",
        model_provider="ollama",
        model_name="local-model",
        ollama_base_url="http://ollama.test",
    )
    provider = OllamaProvider(settings, httpx.MockTransport(success))
    assert "".join([token async for token in provider.stream("system", "question")]) == (
        "Grounded answer"
    )

    failing = OllamaProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"error": "model not found"})
        ),
    )
    with pytest.raises(ProviderUnavailableError, match="rejected"):
        _ = [token async for token in failing.stream("system", "question")]

    malformed = OllamaProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"message": "not-an-object"})
        ),
    )
    with pytest.raises(ProviderUnavailableError, match="invalid streaming response"):
        _ = [token async for token in malformed.stream("system", "question")]


@pytest.mark.asyncio
async def test_openai_compatible_stream_authorization_health_and_errors() -> None:
    def stream_response(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer private-token"
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"content":"Verified "}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
                "data: [DONE]\n\n"
            ),
            headers={"Content-Type": "text/event-stream"},
        )

    settings = Settings(
        environment="test",
        model_provider="openai_compatible",
        model_name="compatible-model",
        openai_base_url="http://provider.test/v1",
        openai_api_key="private-token",
    )
    provider = OpenAICompatibleProvider(settings, httpx.MockTransport(stream_response))
    assert "".join([token async for token in provider.stream("system", "question")]) == (
        "Verified answer"
    )

    healthy = OpenAICompatibleProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"data": [{"id": "compatible-model"}]})
        ),
    )
    assert await healthy.health() == (True, None)

    missing_model = OpenAICompatibleProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"data": [{"id": "other-model"}]})
        ),
    )
    assert await missing_model.health() == (
        False,
        "The configured OpenAI-compatible model is not available (compatible-model)",
    )

    failing = OpenAICompatibleProvider(
        settings,
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"error": {"message": "denied"}})
        ),
    )
    with pytest.raises(ProviderUnavailableError, match="rejected"):
        _ = [token async for token in failing.stream("system", "question")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"choices": {}},
        {"choices": ["not-an-object"]},
        {"choices": [{"delta": "not-an-object"}]},
        {"choices": [{"delta": {"content": 42}}]},
    ],
)
async def test_openai_compatible_rejects_malformed_stream_shapes(
    payload: dict[str, object],
) -> None:
    settings = Settings(
        environment="test",
        model_provider="openai_compatible",
        openai_base_url="http://provider.test/v1",
    )
    provider = OpenAICompatibleProvider(
        settings,
        httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ProviderUnavailableError, match="invalid response"):
        _ = [token async for token in provider.stream("system", "question")]


def test_mock_provider_is_rejected_outside_test_environment() -> None:
    with pytest.raises(ValidationError, match="only in the test environment"):
        Settings(environment="production", model_provider="mock")


@pytest.mark.asyncio
async def test_chat_stream_surfaces_provider_failure() -> None:
    service = ChatService(Settings(), UnusedRetriever(), UnavailableProvider())  # type: ignore[arg-type]
    with pytest.raises(ProviderUnavailableError, match="Provider unavailable"):
        _ = [token async for token in service.tokens("grounded prompt")]
