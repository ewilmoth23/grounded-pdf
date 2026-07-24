from __future__ import annotations

from collections.abc import AsyncIterator


class MockChatProvider:
    async def stream(self, system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
        del system_prompt
        source_line = next(
            (line for line in user_prompt.splitlines() if line.startswith("SOURCE ")), ""
        )
        marker = source_line.removeprefix("SOURCE ").strip()
        context = user_prompt.split("CONTEXT", 1)[-1].split("QUESTION", 1)[0].strip()
        excerpt = " ".join(context.split())[:260]
        answer = f"Based on the selected document, {excerpt} {marker}".strip()
        for start in range(0, len(answer), 24):
            yield answer[start : start + 24]

    async def health(self) -> tuple[bool, str | None]:
        return True, None
