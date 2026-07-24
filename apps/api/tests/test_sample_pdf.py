from collections.abc import Callable
from pathlib import Path
from runpy import run_path
from typing import cast

import fitz


def test_sample_pdf_generation_is_reproducible(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[3] / "scripts" / "generate_sample_pdf.py"
    generate = cast(Callable[[Path], None], run_path(str(script))["generate_sample_pdf"])
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"

    generate(first)
    generate(second)

    assert first.read_bytes() == second.read_bytes()
    with fitz.open(first) as document:
        assert document.page_count == 3
        assert "37 percent" in document.load_page(1).get_text()
