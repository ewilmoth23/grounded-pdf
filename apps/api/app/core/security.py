from __future__ import annotations

import re
from pathlib import Path

SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def display_filename(original: str) -> str:
    name = Path(original).name
    cleaned = SAFE_FILENAME_RE.sub("_", name).strip(" .")
    return (cleaned or "document.pdf")[:240]


def secure_document_path(upload_dir: Path, storage_name: str) -> Path:
    root = upload_dir.resolve()
    candidate = (root / storage_name).resolve()
    if candidate.parent != root:
        raise ValueError("Unsafe document path")
    return candidate
