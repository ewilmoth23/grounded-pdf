import pytest

from app.services.chunking import create_chunks
from app.services.pdf import normalize_text


def test_chunks_include_overlap_and_offsets() -> None:
    text = "First paragraph has useful evidence. " * 12
    chunks = create_chunks(text, chunk_size=120, overlap=25)
    assert len(chunks) > 2
    assert chunks[0].index == 0
    assert chunks[0].start_offset == 0
    assert chunks[1].start_offset < chunks[0].end_offset
    assert text[chunks[1].start_offset : chunks[1].end_offset] == chunks[1].raw_text


def test_empty_text_and_invalid_overlap() -> None:
    assert create_chunks("  ", chunk_size=200, overlap=20) == []
    with pytest.raises(ValueError, match="overlap"):
        create_chunks("content", chunk_size=200, overlap=200)


def test_raw_chunk_text_and_offsets_survive_normalization() -> None:
    text = "First   line with evidence.\n\nSecond\tline with more evidence."
    chunks = create_chunks(text, chunk_size=200, overlap=20, normalizer=normalize_text)

    assert chunks[0].raw_text == text
    assert chunks[0].normalized_text == (
        "First line with evidence.\n\nSecond line with more evidence."
    )
    assert text[chunks[0].start_offset : chunks[0].end_offset] == chunks[0].raw_text
