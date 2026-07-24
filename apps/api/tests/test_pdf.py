from pathlib import Path

import fitz
import pytest

from app.core.exceptions import FileValidationError
from app.core.security import display_filename, secure_document_path
from app.services.pdf import (
    MAX_OUTLINE_ENTRIES,
    OutlineEntry,
    extract_pdf,
    normalize_text,
    outline_from_toc,
    validate_pdf,
)


def test_pdf_validation_and_page_metadata(sample_pdf: Path) -> None:
    validate_pdf(sample_pdf, "sample.pdf")
    result = extract_pdf(sample_pdf)
    assert result.title == "GroundedPDF Sample Report"
    assert result.page_count == 2
    assert result.pages[0].page_number == 1
    assert result.pages[1].page_number == 2
    assert "37 percent" in result.pages[1].normalized_text
    assert all(page.extraction_method == "pymupdf" for page in result.pages)


def test_rejects_corrupt_and_mislabeled_files(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"not-a-pdf")
    with pytest.raises(FileValidationError, match="not a valid PDF"):
        validate_pdf(corrupt, "corrupt.pdf")
    with pytest.raises(FileValidationError, match=r"Only \.pdf"):
        validate_pdf(corrupt, "notes.txt")


def test_rejects_password_protected_pdf(tmp_path: Path) -> None:
    protected = tmp_path / "protected.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Protected document")
    document.save(
        protected,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="user-password",
    )
    document.close()

    with pytest.raises(FileValidationError, match="Password-protected"):
        validate_pdf(protected, "protected.pdf")


def test_extract_pdf_captures_document_outline(tmp_path: Path) -> None:
    path = tmp_path / "outlined.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Introduction body text for the first chapter.")
    document.new_page().insert_text((72, 72), "Findings body text for the second chapter.")
    document.set_toc([[1, "Introduction", 1], [2, "Background", 1], [1, "Findings", 2]])
    document.save(path)
    document.close()

    result = extract_pdf(path)

    assert result.outline == [
        OutlineEntry(level=1, title="Introduction", page=1),
        OutlineEntry(level=2, title="Background", page=1),
        OutlineEntry(level=1, title="Findings", page=2),
    ]


def test_extract_pdf_without_bookmarks_has_empty_outline(sample_pdf: Path) -> None:
    assert extract_pdf(sample_pdf).outline == []


def test_outline_from_toc_bounds_titles_pages_and_entry_count() -> None:
    toc: list[list[object]] = [
        [1, "X" * 400, 1],  # over-long title is truncated
        [0, "Clamped level", 0],  # level and page are clamped to at least 1
        [1, "Beyond the last page", 99],  # page is clamped to the page count
        [1, "   ", 1],  # blank titles are dropped
        [1, "Bad page", "not-a-page"],  # malformed entries are dropped
        *[[1, f"Section {index}", 2] for index in range(MAX_OUTLINE_ENTRIES)],
    ]

    entries = outline_from_toc(toc, page_count=3)

    assert len(entries) == MAX_OUTLINE_ENTRIES
    assert entries[0] == OutlineEntry(level=1, title="X" * 300, page=1)
    assert entries[1] == OutlineEntry(level=1, title="Clamped level", page=1)
    assert entries[2] == OutlineEntry(level=1, title="Beyond the last page", page=3)
    assert all(1 <= entry.page <= 3 for entry in entries)


def test_normalization_preserves_paragraphs() -> None:
    assert normalize_text("A   sentence.\n\n\n  Second\tline. ") == "A sentence.\n\nSecond line."


def test_optional_ocr_replaces_unsearchable_page_text(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    class FakeOcr:
        def extract(self, document: fitz.Document, page_number: int) -> str:
            # The already-open document is passed in; OCR must not reopen the file.
            assert document.page_count == 1
            assert page_number == 1
            return "Tesseract recovered enough verified text from this scanned page."

    result = extract_pdf(path, ocr=FakeOcr(), enable_ocr=True)

    assert result.pages[0].is_searchable is True
    assert result.pages[0].extraction_method == "tesseract"
    assert "recovered enough verified text" in result.pages[0].normalized_text


def test_filename_and_path_traversal_protection(tmp_path: Path) -> None:
    assert display_filename("../../private/report.pdf") == "report.pdf"
    with pytest.raises(ValueError, match="Unsafe"):
        secure_document_path(tmp_path, "../escape.pdf")
