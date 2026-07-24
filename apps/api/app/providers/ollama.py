from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import HEALTH_CHECK_TIMEOUT_SECONDS


class OllamaProvider:
    def __init__(
        self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create one shared connection-pooling client per provider instance."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(transport=self.transport)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        payload = {
            "model": self.settings.model_name,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self.settings.temperature,
                "num_predict": self.settings.max_output_tokens,
            },
        }
        try:
            client = self._get_client()
            async with client.stream(
                "POST",
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json=payload,
                timeout=httpx.Timeout(self.settings.model_timeout_seconds),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        raise ProviderUnavailableError(
                            "Ollama returned an invalid streaming response."
                        )
                    if data.get("error"):
                        raise ProviderUnavailableError(
                            "Ollama rejected the request. Confirm that the configured model "
                            f"is installed ({self.settings.model_name})."
                        )
                    message = data.get("message")
                    if message is None and data.get("done") is True:
                        continue
                    if not isinstance(message, dict):
                        raise ProviderUnavailableError(
                            "Ollama returned an invalid streaming response."
                        )
                    token = message.get("content", "")
                    if not isinstance(token, str):
                        raise ProviderUnavailableError(
                            "Ollama returned an invalid streaming response."
                        )
                    if token:
                        yield token
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ProviderUnavailableError(
                "Ollama is unavailable. Start Ollama and pull the configured model "
                f"({self.settings.model_name})."
            ) from exc

    async def health(self) -> tuple[bool, str | None]:
        try:
            response = await self._get_client().get(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/tags",
                timeout=HEALTH_CHECK_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
                return False, "Ollama returned an invalid model list"
            available_names = {
                name
                for model in payload["models"]
                if isinstance(model, dict)
                for key in ("name", "model")
                if isinstance((name := model.get(key)), str)
            }
            configured_names = {self.settings.model_name}
            if ":" not in self.settings.model_name.rsplit("/", maxsplit=1)[-1]:
                configured_names.add(f"{self.settings.model_name}:latest")
            if available_names.isdisjoint(configured_names):
                return (
                    False,
                    f"Configured Ollama model is not installed ({self.settings.model_name})",
                )
            return True, None
        except (httpx.HTTPError, ValueError, TypeError):
            return False, "Ollama is not reachable"
