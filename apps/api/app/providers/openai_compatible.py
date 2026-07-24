from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import HEALTH_CHECK_TIMEOUT_SECONDS


class OpenAICompatibleProvider:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create one shared connection-pooling client per provider instance."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(headers=self.headers, transport=self.transport)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    @property
    def headers(self) -> dict[str, str]:
        if not self.settings.openai_api_key:
            return {}
        return {"Authorization": f"Bearer {self.settings.openai_api_key}"}

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        payload = {
            "model": self.settings.model_name,
            "stream": True,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_output_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            client = self._get_client()
            async with client.stream(
                "POST",
                f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
                json=payload,
                timeout=httpx.Timeout(self.settings.model_timeout_seconds),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                    elif line.startswith("{"):
                        data = json.loads(line)
                    else:
                        continue
                    if not isinstance(data, dict):
                        raise ProviderUnavailableError(
                            "The configured OpenAI-compatible endpoint returned an invalid "
                            "response."
                        )
                    if data.get("error"):
                        raise ProviderUnavailableError(
                            "The configured OpenAI-compatible endpoint rejected the request."
                        )
                    choices = data.get("choices")
                    if not isinstance(choices, list):
                        raise ProviderUnavailableError(
                            "The configured OpenAI-compatible endpoint returned an invalid "
                            "response."
                        )
                    if not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict) or not isinstance(choice.get("delta"), dict):
                        raise ProviderUnavailableError(
                            "The configured OpenAI-compatible endpoint returned an invalid "
                            "response."
                        )
                    token = choice["delta"].get("content", "")
                    if token is None:
                        continue
                    if not isinstance(token, str):
                        raise ProviderUnavailableError(
                            "The configured OpenAI-compatible endpoint returned an invalid "
                            "response."
                        )
                    if token:
                        yield token
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
            raise ProviderUnavailableError(
                "The configured OpenAI-compatible model endpoint is unavailable."
            ) from exc

    async def health(self) -> tuple[bool, str | None]:
        try:
            response = await self._get_client().get(
                f"{self.settings.openai_base_url.rstrip('/')}/models",
                timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                return False, "The OpenAI-compatible endpoint returned an invalid model list"
            available_models = {
                model_id
                for model in payload["data"]
                if isinstance(model, dict)
                if isinstance((model_id := model.get("id")), str)
            }
            if self.settings.model_name not in available_models:
                return (
                    False,
                    "The configured OpenAI-compatible model is not available "
                    f"({self.settings.model_name})",
                )
            return True, None
        except (httpx.HTTPError, ValueError, TypeError):
            return False, "The OpenAI-compatible endpoint is not reachable"
