from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import FileValidationError
from app.core.security import display_filename, secure_document_path


@dataclass(frozen=True)
class StoredUpload:
    original_name: str
    storage_name: str
    path: Path
    size: int
    sha256: str


async def store_upload(file: UploadFile, upload_dir: Path, max_bytes: int) -> StoredUpload:
    original_name = display_filename(file.filename or "document.pdf")
    if Path(original_name).suffix.lower() != ".pdf":
        await file.close()
        raise FileValidationError("Only .pdf files are supported", "unsupported_extension")
    if file.content_type not in {
        None,
        "",
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
    }:
        await file.close()
        raise FileValidationError(
            "The uploaded file must use a PDF content type", "unsupported_content_type"
        )

    storage_name = f"{uuid.uuid4()}.pdf"
    destination = secure_document_path(upload_dir, storage_name)
    digest = hashlib.sha256()
    size = 0
    try:
        with destination.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise FileValidationError(
                        f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit",
                        "file_too_large",
                    )
                digest.update(chunk)
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        destination.unlink(missing_ok=True)
        raise FileValidationError("The uploaded file is empty", "empty_file")
    return StoredUpload(
        original_name=original_name,
        storage_name=storage_name,
        path=destination,
        size=size,
        sha256=digest.hexdigest(),
    )
