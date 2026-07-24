from pathlib import Path

import fitz
import pytest

from app.core.exceptions import FileValidationError
from app.core.security import display_filename, secure_document_path
from app.services.pdf import extract_pdf, normalize_text, validate_pdf


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


def test_normalization_preserves_paragraphs() -> None:
    assert normalize_text("A   sentence.\n\n\n  Second\tline. ") == "A sentence.\n\nSecond line."


def test_optional_ocr_replaces_unsearchable_page_text(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    class FakeOcr:
        def extract(self, document_path: Path, page_number: int) -> str:
            assert document_path == path
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
