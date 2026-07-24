from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import fitz

from app.core.exceptions import FileValidationError

WHITESPACE_RE = re.compile(r"[\t\u00a0 ]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")
MIN_SEARCHABLE_CHARACTERS = 24


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    raw_text: str
    normalized_text: str
    extraction_method: str
    is_searchable: bool


@dataclass(frozen=True)
class ExtractedDocument:
    title: str | None
    page_count: int
    pages: list[ExtractedPage]


class OcrExtractor(Protocol):
    def extract(self, document_path: Path, page_number: int) -> str: ...


class TesseractOcrExtractor:
    """Render one PDF page and extract its text with an optional local Tesseract install."""

    def __init__(self, scale: float = 2.0) -> None:
        self.scale = scale

    def extract(self, document_path: Path, page_number: int) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise FileValidationError(
                "OCR is enabled, but the optional OCR dependencies are not installed.",
                "ocr_unavailable",
            ) from exc

        try:
            with fitz.open(document_path) as document:
                page = document.load_page(page_number - 1)
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(self.scale, self.scale),
                    colorspace=fitz.csRGB,
                    alpha=False,
                )
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            try:
                return str(pytesseract.image_to_string(image))
            finally:
                image.close()
        except pytesseract.TesseractNotFoundError as exc:
            raise FileValidationError(
                "OCR is enabled, but the Tesseract executable is not installed or not on PATH.",
                "ocr_unavailable",
            ) from exc
        except FileValidationError:
            raise
        except (fitz.FileDataError, RuntimeError, ValueError, OSError) as exc:
            raise FileValidationError("OCR failed for a scanned PDF page.", "ocr_failed") from exc


def normalize_text(text: str) -> str:
    lines = [WHITESPACE_RE.sub(" ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    normalized = "\n".join(lines)
    return BLANK_LINES_RE.sub("\n\n", normalized).strip()


def validate_pdf(path: Path, original_name: str) -> None:
    if Path(original_name).suffix.lower() != ".pdf":
        raise FileValidationError("Only .pdf files are supported", "unsupported_extension")
    try:
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise FileValidationError(
                    "The uploaded file is not a valid PDF", "invalid_signature"
                )
        with fitz.open(path) as document:
            if document.needs_pass:
                raise FileValidationError(
                    "Password-protected PDFs are not supported", "password_protected"
                )
            if document.page_count < 1:
                raise FileValidationError("The PDF has no pages", "empty_pdf")
            document.load_page(0)
    except FileValidationError:
        raise
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise FileValidationError("The PDF is corrupt or cannot be read", "corrupt_pdf") from exc


def extract_pdf(
    path: Path, *, ocr: OcrExtractor | None = None, enable_ocr: bool = False
) -> ExtractedDocument:
    try:
        with fitz.open(path) as document:
            if document.needs_pass:
                raise FileValidationError(
                    "Password-protected PDFs are not supported", "password_protected"
                )
            metadata = document.metadata or {}
            title = (metadata.get("title") or "").strip() or None
            pages: list[ExtractedPage] = []
            for index, page in enumerate(document):
                raw_text = page.get_text("text", sort=True)
                normalized = normalize_text(raw_text)
                method = "pymupdf"
                if len(normalized) < MIN_SEARCHABLE_CHARACTERS and enable_ocr and ocr:
                    ocr_text = ocr.extract(path, index + 1)
                    if len(normalize_text(ocr_text)) > len(normalized):
                        raw_text = ocr_text
                        normalized = normalize_text(ocr_text)
                        method = "tesseract"
                pages.append(
                    ExtractedPage(
                        page_number=index + 1,
                        raw_text=raw_text,
                        normalized_text=normalized,
                        extraction_method=method,
                        is_searchable=len(normalized) >= MIN_SEARCHABLE_CHARACTERS,
                    )
                )
            return ExtractedDocument(title=title, page_count=document.page_count, pages=pages)
    except FileValidationError:
        raise
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise FileValidationError("PDF text extraction failed", "extraction_failed") from exc
