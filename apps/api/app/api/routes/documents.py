from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import FileValidationError, GroundedPdfError
from app.db.session import get_db
from app.models.entities import Document, ProcessingStatus
from app.rag.verification import clear_verification_cache
from app.schemas.common import DeleteResponse
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentResponse,
    OutlineEntry,
    ProcessingStatusResponse,
    RejectedUpload,
    ReprocessStaleResponse,
    UploadResponse,
)
from app.services.dependencies import get_vector_store
from app.services.documents import (
    create_document_from_upload,
    delete_document,
    document_details,
    document_file_path,
    is_stale_index,
    parse_outline,
)
from app.services.settings import effective_settings, index_fingerprint
from app.workers.ingestion import process_document

router = APIRouter()


def require_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise GroundedPdfError("Document not found", code="document_not_found", status_code=404)
    return document


@router.post("", response_model=UploadResponse, status_code=202)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    if len(files) > settings.max_upload_files:
        raise GroundedPdfError(
            f"A maximum of {settings.max_upload_files} files can be uploaded at once",
            code="too_many_files",
            status_code=422,
        )
    aggregate_size = sum(file.size or 0 for file in files)
    if aggregate_size > settings.max_upload_batch_bytes:
        raise GroundedPdfError(
            f"Uploaded files exceed the {settings.max_upload_batch_mb} MB batch limit",
            code="upload_batch_too_large",
            status_code=413,
        )
    accepted: dict[str, DocumentResponse] = {}
    rejected: list[RejectedUpload] = []
    for file in files:
        filename = file.filename or "unnamed"
        try:
            document, duplicate = await create_document_from_upload(db, file, settings)
            accepted[document.id] = DocumentResponse.model_validate(document)
            if not duplicate:
                background_tasks.add_task(process_document, document.id)
        except FileValidationError as exc:
            rejected.append(RejectedUpload(filename=filename, code=exc.code, message=exc.message))
    return UploadResponse(documents=list(accepted.values()), rejected=rejected)


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentResponse]:
    fingerprint = index_fingerprint(effective_settings(db, settings))
    total = db.scalar(select(func.count(Document.id))) or 0
    response.headers["X-Total-Count"] = str(total)
    responses: list[DocumentResponse] = []
    for document in db.scalars(
        select(Document)
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit)
        .offset(offset)
    ):
        item = DocumentResponse.model_validate(document)
        item.stale_index = is_stale_index(document, fingerprint)
        responses.append(item)
    return responses


# Each queued document triggers a full re-ingestion; claim a bounded batch per
# call so one request cannot fan out unbounded background work.
REPROCESS_BATCH_LIMIT = 25


@router.post("/reprocess-stale", response_model=ReprocessStaleResponse, status_code=202)
def reprocess_stale_documents(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReprocessStaleResponse:
    """Queue re-ingestion for stale ready documents, a bounded batch per call."""
    fingerprint = index_fingerprint(effective_settings(db, settings))

    def stale_ready_ids() -> list[str]:
        return [
            document.id
            for document in db.scalars(
                select(Document)
                .where(Document.status == ProcessingStatus.READY)
                .order_by(Document.created_at)
            )
            if is_stale_index(document, fingerprint)
        ]

    queued = 0
    for document_id in stale_ready_ids()[:REPROCESS_BATCH_LIMIT]:
        claim = db.execute(
            update(Document)
            .where(Document.id == document_id, Document.status == ProcessingStatus.READY)
            .values(status=ProcessingStatus.QUEUED, processing_error=None)
        )
        if getattr(claim, "rowcount", 0) != 1:
            continue
        queued += 1
        background_tasks.add_task(process_document, document_id)
    db.commit()
    # Reprocessing changes the evidence behind cached verification verdicts.
    clear_verification_cache()
    return ReprocessStaleResponse(queued=queued, remaining=len(stale_ready_ids()))


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DocumentDetailResponse:
    document = require_document(db, document_id)
    scanned_pages, chunk_count = document_details(db, document)
    response = DocumentDetailResponse.model_validate(document)
    response.scanned_page_numbers = scanned_pages
    response.chunk_count = chunk_count
    response.stale_index = is_stale_index(
        document, index_fingerprint(effective_settings(db, settings))
    )
    outline = parse_outline(document.outline_json)
    response.outline = (
        [OutlineEntry.model_validate(entry) for entry in outline] if outline else None
    )
    return response


@router.get("/{document_id}/status", response_model=ProcessingStatusResponse)
def get_processing_status(
    document_id: str, db: Session = Depends(get_db)
) -> ProcessingStatusResponse:
    document = require_document(db, document_id)
    return ProcessingStatusResponse(
        id=document.id,
        status=document.status,
        processing_error=document.processing_error,
        page_count=document.page_count,
        searchable_page_count=document.searchable_page_count,
    )


@router.get("/{document_id}/file", response_class=FileResponse)
def get_document_file(
    document_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    document = require_document(db, document_id)
    if document.status == ProcessingStatus.DELETED:
        raise GroundedPdfError(
            "Document deletion is incomplete", code="document_deleting", status_code=404
        )
    return FileResponse(
        document_file_path(document, settings),
        media_type="application/pdf",
        filename=document.original_name,
        content_disposition_type="inline",
    )


@router.post("/{document_id}/retry", response_model=DocumentResponse, status_code=202)
def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Document:
    document = require_document(db, document_id)
    if document.status == ProcessingStatus.DELETED:
        raise GroundedPdfError(
            "This document is pending deletion", code="document_deleting", status_code=409
        )
    if document.status not in {ProcessingStatus.FAILED, ProcessingStatus.READY}:
        raise GroundedPdfError(
            "This document is already queued or processing",
            code="already_processing",
            status_code=409,
        )
    claim = db.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.status.in_([ProcessingStatus.FAILED, ProcessingStatus.READY]),
        )
        .values(status=ProcessingStatus.QUEUED, processing_error=None)
    )
    if getattr(claim, "rowcount", 0) != 1:
        db.rollback()
        raise GroundedPdfError(
            "Document state changed; refresh before retrying",
            code="document_state_changed",
            status_code=409,
        )
    db.commit()
    db.refresh(document)
    background_tasks.add_task(process_document, document.id)
    return document


@router.delete("/{document_id}", response_model=DeleteResponse)
def remove_document(
    document_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DeleteResponse:
    document = require_document(db, document_id)
    delete_document(db, document, settings, get_vector_store())
    return DeleteResponse(deleted=True, id=document_id)
