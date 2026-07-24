from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import GroundedPdfError
from app.core.security import secure_document_path
from app.db.session import SessionLocal
from app.models.entities import (
    Document,
    DocumentChunk,
    DocumentPage,
    ProcessingJob,
    ProcessingStatus,
)
from app.services.chunking import create_chunks
from app.services.dependencies import get_embedding_provider, get_vector_store
from app.services.embeddings import EmbeddingProvider
from app.services.pdf import (
    ExtractedDocument,
    TesseractOcrExtractor,
    extract_pdf,
    normalize_text,
)
from app.services.settings import effective_settings, index_fingerprint
from app.services.vector_store import VectorRecord, VectorStore

logger = logging.getLogger(__name__)


def _serialize_outline(extracted: ExtractedDocument) -> str | None:
    if not extracted.outline:
        return None
    return json.dumps(
        [
            {"level": entry.level, "title": entry.title, "page": entry.page}
            for entry in extracted.outline
        ]
    )


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.vector_store = vector_store

    def process(self, db: Session, document_id: str) -> None:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("processing_document_missing", extra={"document_id": document_id})
            return
        attempt = (
            db.scalar(
                select(func.count(ProcessingJob.id)).where(ProcessingJob.document_id == document_id)
            )
            or 0
        )
        job = ProcessingJob(
            document_id=document_id,
            status=ProcessingStatus.PROCESSING,
            attempt=attempt + 1,
            started_at=datetime.now(UTC),
        )
        claim = db.execute(
            update(Document)
            .where(
                Document.id == document_id,
                Document.status.in_(
                    [
                        ProcessingStatus.QUEUED,
                        ProcessingStatus.FAILED,
                        ProcessingStatus.READY,
                    ]
                ),
            )
            .values(status=ProcessingStatus.PROCESSING, processing_error=None)
        )
        if getattr(claim, "rowcount", 0) != 1:
            db.rollback()
            logger.warning("processing_claim_rejected", extra={"document_id": document_id})
            return
        db.add(job)
        db.commit()
        db.refresh(document)
        started = time.monotonic()
        logger.info("extraction_started", extra={"document_id": document_id})

        try:
            path = secure_document_path(self.settings.upload_dir, document.storage_name)
            if not path.is_file():
                raise FileNotFoundError("The stored PDF file is missing")
            ocr = TesseractOcrExtractor() if self.settings.enable_ocr else None
            extracted = extract_pdf(path, ocr=ocr, enable_ocr=self.settings.enable_ocr)

            self.vector_store.delete_document(document_id)
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            db.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
            db.flush()

            pending_chunks: list[DocumentChunk] = []
            for extracted_page in extracted.pages:
                page = DocumentPage(
                    document_id=document_id,
                    page_number=extracted_page.page_number,
                    raw_text=extracted_page.raw_text,
                    normalized_text=extracted_page.normalized_text,
                    extraction_method=extracted_page.extraction_method,
                    is_searchable=extracted_page.is_searchable,
                    character_count=len(extracted_page.normalized_text),
                )
                db.add(page)
                db.flush()
                if not extracted_page.is_searchable:
                    continue
                for extracted_chunk in create_chunks(
                    extracted_page.raw_text,
                    chunk_size=self.settings.chunk_size,
                    overlap=self.settings.chunk_overlap,
                    normalizer=normalize_text,
                ):
                    pending_chunks.append(
                        DocumentChunk(
                            document_id=document_id,
                            page_id=page.id,
                            page_number=extracted_page.page_number,
                            chunk_index=extracted_chunk.index,
                            raw_text=extracted_chunk.raw_text,
                            normalized_text=extracted_chunk.normalized_text,
                            start_offset=extracted_chunk.start_offset,
                            end_offset=extracted_chunk.end_offset,
                            embedding_id=(
                                f"{document_id}:{extracted_page.page_number}:"
                                f"{extracted_chunk.index}"
                            ),
                            extraction_method=extracted_page.extraction_method,
                        )
                    )
            if not pending_chunks:
                message = (
                    "OCR did not find searchable text in this document."
                    if self.settings.enable_ocr
                    else "No searchable text was found. Install and enable OCR for scanned PDFs."
                )
                document.title = (extracted.title or "")[:500] or None
                document.page_count = extracted.page_count
                document.searchable_page_count = 0
                document.outline_json = _serialize_outline(extracted)
                document.index_fingerprint = None
                document.status = ProcessingStatus.FAILED
                document.processing_error = message
                job.status = ProcessingStatus.FAILED
                job.error = message
                job.completed_at = datetime.now(UTC)
                db.commit()
                logger.warning(
                    "processing_no_searchable_text",
                    extra={"document_id": document_id, "count": extracted.page_count},
                )
                return

            vectors = self.embeddings.embed(
                [stored_chunk.normalized_text for stored_chunk in pending_chunks]
            )
            for stored_chunk in pending_chunks:
                db.add(stored_chunk)
            db.flush()
            self.vector_store.upsert(
                [
                    VectorRecord(
                        id=stored_chunk.embedding_id,
                        text=stored_chunk.normalized_text,
                        embedding=vector,
                        metadata={
                            "document_id": document_id,
                            "document_name": document.original_name,
                            "page_number": stored_chunk.page_number,
                            "chunk_index": stored_chunk.chunk_index,
                            "chunk_id": stored_chunk.id,
                        },
                    )
                    for stored_chunk, vector in zip(pending_chunks, vectors, strict=True)
                ]
            )
            document.title = (extracted.title or "")[:500] or None
            document.page_count = extracted.page_count
            document.searchable_page_count = sum(page.is_searchable for page in extracted.pages)
            document.outline_json = _serialize_outline(extracted)
            document.index_fingerprint = index_fingerprint(self.settings)
            document.status = ProcessingStatus.READY
            job.status = ProcessingStatus.READY
            job.completed_at = datetime.now(UTC)
            db.commit()
            logger.info(
                "extraction_completed",
                extra={
                    "document_id": document_id,
                    "count": len(pending_chunks),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )
        except Exception as exc:
            db.rollback()
            try:
                self.vector_store.delete_document(document_id)
            except Exception:
                logger.exception(
                    "processing_vector_cleanup_failed", extra={"document_id": document_id}
                )
            self._mark_failed(db, document_id, job.id, exc)
            logger.exception("processing_failed", extra={"document_id": document_id})

    @staticmethod
    def _mark_failed(db: Session, document_id: str, job_id: str, exc: Exception) -> None:
        safe_message = (
            str(exc)
            if isinstance(exc, (GroundedPdfError, FileNotFoundError))
            else "Document processing failed. Check the server logs for details."
        )
        document = db.get(Document, document_id)
        job = db.get(ProcessingJob, job_id)
        if document:
            document.status = ProcessingStatus.FAILED
            document.processing_error = safe_message[:1000]
        if job:
            job.status = ProcessingStatus.FAILED
            job.error = safe_message[:1000]
            job.completed_at = datetime.now(UTC)
        db.commit()


def process_document(document_id: str) -> None:
    try:
        with SessionLocal() as db:
            settings = effective_settings(db, get_settings())
            service = IngestionService(settings, get_embedding_provider(), get_vector_store())
            service.process(db, document_id)
    except Exception:
        logger.exception("processing_worker_crashed", extra={"document_id": document_id})
        _mark_document_failed_best_effort(document_id)


def _mark_document_failed_best_effort(document_id: str) -> None:
    """Record a FAILED status with its own session when the worker crashes unexpectedly."""
    try:
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if document is None:
                return
            document.status = ProcessingStatus.FAILED
            document.processing_error = (
                "Document processing failed. Check the server logs for details."
            )
            db.commit()
    except Exception:
        logger.exception("processing_failure_marker_failed", extra={"document_id": document_id})


def recover_interrupted_ingestion(db: Session) -> int:
    """Make work abandoned by a previous API process explicitly retryable."""
    if not inspect(db.get_bind()).has_table(Document.__tablename__):
        return 0
    documents = list(
        db.scalars(
            select(Document).where(
                Document.status.in_([ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING])
            )
        )
    )
    if not documents:
        return 0
    document_ids = [document.id for document in documents]
    message = "Processing was interrupted by an application restart. Retry this document."
    for document in documents:
        document.status = ProcessingStatus.FAILED
        document.processing_error = message
    for job in db.scalars(
        select(ProcessingJob).where(
            ProcessingJob.document_id.in_(document_ids),
            ProcessingJob.status == ProcessingStatus.PROCESSING,
        )
    ):
        job.status = ProcessingStatus.FAILED
        job.error = message
        job.completed_at = datetime.now(UTC)
    db.commit()
    logger.warning("interrupted_ingestion_recovered", extra={"count": len(documents)})
    return len(documents)
