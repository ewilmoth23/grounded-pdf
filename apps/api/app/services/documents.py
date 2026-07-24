from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import FileValidationError, GroundedPdfError
from app.core.security import secure_document_path
from app.models.entities import Document, DocumentChunk, DocumentPage, ProcessingStatus
from app.rag.verification import clear_verification_cache
from app.services.pdf import validate_pdf
from app.services.storage import StoredUpload, store_upload
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)
DELETION_RETRY_MESSAGE = "Deletion could not be completed. Retry deleting this document."


async def create_document_from_upload(
    db: Session, file: UploadFile, settings: Settings
) -> tuple[Document, bool]:
    stored = await store_upload(file, settings.upload_dir, settings.max_upload_bytes)
    return await run_in_threadpool(_register_stored_upload, db, stored, settings)


def _register_stored_upload(
    db: Session, stored: StoredUpload, settings: Settings
) -> tuple[Document, bool]:
    """Validate and persist a stored upload; runs in a worker thread."""
    try:
        validate_pdf(stored.path, stored.original_name)
        existing = db.scalar(select(Document).where(Document.sha256 == stored.sha256))
        if existing:
            return _resolve_duplicate(db, existing, stored, settings)
        document = _document_from_stored(stored)
        db.add(document)
        try:
            db.commit()
        except IntegrityError:
            # A concurrent request persisted the same PDF between our duplicate
            # check and this commit; fall back to the duplicate-handling path.
            db.rollback()
            existing = db.scalar(select(Document).where(Document.sha256 == stored.sha256))
            if existing is None:
                raise
            logger.info("duplicate_upload_race_resolved", extra={"document_id": existing.id})
            return _resolve_duplicate(db, existing, stored, settings)
        db.refresh(document)
        logger.info("document_uploaded", extra={"document_id": document.id})
        return document, False
    except Exception:
        db.rollback()
        stored.path.unlink(missing_ok=True)
        raise


def _resolve_duplicate(
    db: Session, existing: Document, stored: StoredUpload, settings: Settings
) -> tuple[Document, bool]:
    if existing.status == ProcessingStatus.DELETED:
        stored.path.unlink(missing_ok=True)
        raise FileValidationError(
            "An earlier deletion of this PDF is incomplete. Retry deletion first.",
            "deletion_incomplete",
        )
    existing_path = secure_document_path(settings.upload_dir, existing.storage_name)
    if not existing_path.is_file():
        stored.path.replace(existing_path)
        existing.original_name = stored.original_name
        existing.file_size = stored.size
        existing.status = ProcessingStatus.QUEUED
        existing.processing_error = None
        db.commit()
        db.refresh(existing)
        logger.warning("missing_document_file_restored", extra={"document_id": existing.id})
        return existing, False
    stored.path.unlink(missing_ok=True)
    return existing, True


def _document_from_stored(stored: StoredUpload) -> Document:
    return Document(
        original_name=stored.original_name,
        storage_name=stored.storage_name,
        content_type="application/pdf",
        file_size=stored.size,
        sha256=stored.sha256,
        status=ProcessingStatus.QUEUED,
    )


def parse_outline(outline_json: str | None) -> list[dict[str, int | str]] | None:
    """Deserialize the stored outline defensively; malformed data reads as no outline."""
    if not outline_json:
        return None
    try:
        parsed = json.loads(outline_json)
    except json.JSONDecodeError:
        logger.warning("invalid_document_outline_ignored")
        return None
    if not isinstance(parsed, list):
        return None
    entries: list[dict[str, int | str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        level, title, page = item.get("level"), item.get("title"), item.get("page")
        # type() rather than isinstance(): bool is an int subclass and a stored
        # true/false must not read as a valid level or page number.
        if type(level) is int and isinstance(title, str) and type(page) is int:
            entries.append({"level": level, "title": title, "page": page})
    return entries or None


def is_stale_index(document: Document, current_fingerprint: str) -> bool:
    """A ready document indexed under different (or unrecorded) settings is stale."""
    return (
        document.status == ProcessingStatus.READY
        and document.index_fingerprint != current_fingerprint
    )


def document_details(db: Session, document: Document) -> tuple[list[int], int]:
    scanned_pages = list(
        db.scalars(
            select(DocumentPage.page_number)
            .where(DocumentPage.document_id == document.id, DocumentPage.is_searchable.is_(False))
            .order_by(DocumentPage.page_number)
        )
    )
    chunk_count = (
        db.scalar(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document.id)
        )
        or 0
    )
    return scanned_pages, chunk_count


def delete_document(
    db: Session, document: Document, settings: Settings, vector_store: VectorStore
) -> None:
    document_id = document.id
    if document.status != ProcessingStatus.DELETED:
        claim = db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.status.in_([ProcessingStatus.FAILED, ProcessingStatus.READY]),
            )
            .values(status=ProcessingStatus.DELETED, processing_error=None)
        )
        if getattr(claim, "rowcount", 0) != 1:
            db.rollback()
            raise GroundedPdfError(
                "Wait for document processing to finish before deleting it",
                code="document_processing",
                status_code=409,
            )
        db.commit()
        db.refresh(document)

    try:
        path = secure_document_path(settings.upload_dir, document.storage_name)
        vector_store.delete_document(document_id)
        path.unlink(missing_ok=True)
    except Exception as exc:
        document.processing_error = DELETION_RETRY_MESSAGE
        db.commit()
        if isinstance(exc, OSError):
            raise GroundedPdfError(
                "Could not remove the stored PDF", code="file_delete_failed", status_code=500
            ) from exc
        raise

    try:
        db.delete(document)
        db.commit()
    except Exception as exc:
        db.rollback()
        persisted = db.get(Document, document_id)
        if persisted is not None:
            persisted.status = ProcessingStatus.DELETED
            persisted.processing_error = DELETION_RETRY_MESSAGE
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "document_deletion_recovery_failed", extra={"document_id": document_id}
                )
        raise GroundedPdfError(
            "Indexed data was removed, but deletion could not be finalized. Retry deletion.",
            code="deletion_finalize_failed",
            status_code=500,
        ) from exc
    # The deleted document may back cached verification verdicts.
    clear_verification_cache()
    logger.info("document_deleted", extra={"document_id": document_id})


def document_file_path(document: Document, settings: Settings) -> Path:
    path = secure_document_path(settings.upload_dir, document.storage_name)
    if not path.is_file():
        raise GroundedPdfError(
            "The stored PDF file is missing", code="document_file_missing", status_code=404
        )
    return path
