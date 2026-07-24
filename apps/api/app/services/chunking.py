from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    raw_text: str
    normalized_text: str
    start_offset: int
    end_offset: int


def _choose_boundary(text: str, target_end: int, start: int) -> int:
    if target_end >= len(text):
        return len(text)
    lower_bound = start + max(1, (target_end - start) // 2)
    for separator in ("\n\n", "\n", ". ", " "):
        position = text.rfind(separator, lower_bound, target_end)
        if position >= lower_bound:
            return position + len(separator)
    return target_end


def create_chunks(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    normalizer: Callable[[str], str] | None = None,
) -> list[TextChunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    if not text.strip():
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        end = _choose_boundary(text, min(start + chunk_size, len(text)), start)
        raw = text[start:end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw.rstrip())
        chunk_start = start + left_trim
        chunk_end = start + right_trim
        raw_chunk = text[chunk_start:chunk_end]
        normalized = normalizer(raw_chunk) if normalizer else raw_chunk.strip()
        if normalized:
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    raw_text=raw_chunk,
                    normalized_text=normalized,
                    start_offset=chunk_start,
                    end_offset=chunk_end,
                )
            )
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap)
        start = next_start
    return chunks
