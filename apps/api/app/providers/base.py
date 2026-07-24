from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

HEALTH_CHECK_TIMEOUT_SECONDS: float = 3.0


class ChatProvider(Protocol):
    def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]: ...

    async def health(self) -> tuple[bool, str | None]: ...
