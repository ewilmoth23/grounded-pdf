import json
from contextlib import nullcontext
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.exceptions import GroundedPdfError, VectorStoreError
from app.models.entities import (
    ApplicationSetting,
    Citation,
    Conversation,
    ConversationDocument,
    Document,
    DocumentChunk,
    DocumentPage,
    Message,
    MessageRole,
    ProcessingJob,
    ProcessingStatus,
)
from app.services.documents import delete_document
from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.vector_store import InMemoryVectorStore
from app.workers.ingestion import IngestionService, process_document, recover_interrupted_ingestion


def add_document(db: Session, settings: Settings, pdf: Path) -> Document:
    storage_name = "fixed-id.pdf"
    target = settings.upload_dir / storage_name
    target.write_bytes(pdf.read_bytes())
    document = Document(
        original_name="sample.pdf",
        storage_name=storage_name,
        file_size=target.stat().st_size,
        sha256="a" * 64,
        status=ProcessingStatus.QUEUED,
    )
    db.add(document)
    db.commit()
    return document


def test_ingestion_is_idempotent_and_preserves_pages(
    db: Session, settings: Settings, sample_pdf: Path
) -> None:
    document = add_document(db, settings, sample_pdf)
    vectors = InMemoryVectorStore()
    service = IngestionService(settings, DeterministicEmbeddingProvider(), vectors)

    service.process(db, document.id)
    db.refresh(document)
    first_count = db.scalar(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document.id)
    )
    assert document.status == ProcessingStatus.READY
    assert document.page_count == 2
    assert document.searchable_page_count == 2
    assert first_count and first_count > 0
    pages = list(
        db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document.id)
            .order_by(DocumentPage.page_number)
        )
    )
    assert [page.page_number for page in pages] == [1, 2]

    service.process(db, document.id)
    second_count = db.scalar(
        select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document.id)
    )
    assert second_count == first_count
    assert len(vectors.records) == first_count


def test_persisted_chunk_offsets_locate_chunk_text_within_page(
    db: Session, settings: Settings, sample_pdf: Path
) -> None:
    """Stored offsets must slice the page's extracted text exactly (evidence highlighting)."""
    document = add_document(db, settings, sample_pdf)
    service = IngestionService(settings, DeterministicEmbeddingProvider(), InMemoryVectorStore())

    service.process(db, document.id)

    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
    )
    assert chunks
    for chunk in chunks:
        page = db.get(DocumentPage, chunk.page_id)
        assert page is not None
        assert 0 <= chunk.start_offset < chunk.end_offset <= len(page.raw_text)
        assert page.raw_text[chunk.start_offset : chunk.end_offset] == chunk.raw_text


def test_image_only_document_preserves_unsearchable_page_metadata(
    db: Session, settings: Settings, tmp_path: Path
) -> None:
    import fitz

    path = tmp_path / "image-only.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(path)
    pdf.close()
    document = add_document(db, settings, path)
    vectors = InMemoryVectorStore()

    IngestionService(settings, DeterministicEmbeddingProvider(), vectors).process(db, document.id)

    db.refresh(document)
    pages = list(db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id)))
    assert document.status == ProcessingStatus.FAILED
    assert document.page_count == 1
    assert document.searchable_page_count == 0
    assert "enable OCR" in (document.processing_error or "")
    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert pages[0].is_searchable is False
    assert vectors.records == {}


def test_deletion_removes_file_database_rows_and_vectors(
    db: Session, settings: Settings, sample_pdf: Path
) -> None:
    document = add_document(db, settings, sample_pdf)
    vectors = InMemoryVectorStore()
    IngestionService(settings, DeterministicEmbeddingProvider(), vectors).process(db, document.id)
    document_id = document.id
    path = settings.upload_dir / document.storage_name
    conversation = Conversation(title="Deletion test")
    db.add(conversation)
    db.flush()
    db.add(ConversationDocument(conversation_id=conversation.id, document_id=document.id))
    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="A cited answer",
    )
    db.add(message)
    db.flush()
    db.add(
        Citation(
            message_id=message.id,
            document_id=document.id,
            document_name=document.original_name,
            page_number=2,
            excerpt="Evidence",
            retrieval_score=0.9,
            ordinal=1,
        )
    )
    db.commit()

    delete_document(db, document, settings, vectors)

    assert db.get(Document, document_id) is None
    assert not path.exists()
    assert not vectors.records
    assert db.scalar(select(func.count(DocumentPage.id))) == 0
    assert db.scalar(select(func.count(DocumentChunk.id))) == 0
    assert db.scalar(select(func.count(ProcessingJob.id))) == 0
    assert db.scalar(select(func.count(ConversationDocument.document_id))) == 0
    assert db.scalar(select(func.count(Citation.id))) == 0
    assert db.scalar(select(func.count(Message.id))) == 1


def test_failed_deletion_leaves_retryable_tombstone(
    db: Session, settings: Settings, sample_pdf: Path
) -> None:
    document = add_document(db, settings, sample_pdf)
    document.status = ProcessingStatus.FAILED
    db.commit()

    class FailOnceVectorStore(InMemoryVectorStore):
        def __init__(self) -> None:
            super().__init__()
            self.fail = True

        def delete_document(self, document_id: str) -> None:
            if self.fail:
                self.fail = False
                raise VectorStoreError("simulated vector deletion failure")
            super().delete_document(document_id)

    vectors = FailOnceVectorStore()
    path = settings.upload_dir / document.storage_name

    with pytest.raises(VectorStoreError, match="simulated"):
        delete_document(db, document, settings, vectors)

    db.refresh(document)
    assert document.status == ProcessingStatus.DELETED
    assert "Retry deleting" in (document.processing_error or "")
    assert path.exists()

    delete_document(db, document, settings, vectors)
    assert db.get(Document, document.id) is None
    assert not path.exists()


@pytest.mark.parametrize("status", [ProcessingStatus.PROCESSING, ProcessingStatus.DELETED])
def test_ingestion_does_not_run_without_an_atomic_claim(
    db: Session, settings: Settings, sample_pdf: Path, status: ProcessingStatus
) -> None:
    document = add_document(db, settings, sample_pdf)
    document.status = status
    db.commit()
    vectors = InMemoryVectorStore()

    IngestionService(settings, DeterministicEmbeddingProvider(), vectors).process(db, document.id)

    db.refresh(document)
    assert document.status == status
    assert db.scalar(select(func.count(ProcessingJob.id))) == 0
    assert vectors.records == {}


def test_stale_delete_cannot_overwrite_an_ingestion_claim(
    db: Session, settings: Settings, sample_pdf: Path
) -> None:
    document = add_document(db, settings, sample_pdf)
    document.status = ProcessingStatus.READY
    db.commit()
    stale_session = sessionmaker(bind=db.get_bind(), expire_on_commit=False)()
    stale_document = stale_session.get(Document, document.id)
    assert stale_document is not None
    document.status = ProcessingStatus.PROCESSING
    db.commit()

    with pytest.raises(GroundedPdfError) as exc_info:
        delete_document(stale_session, stale_document, settings, InMemoryVectorStore())

    stale_session.close()
    assert exc_info.value.code == "document_processing"
    db.refresh(document)
    assert document.status == ProcessingStatus.PROCESSING
    assert (settings.upload_dir / document.storage_name).exists()


def test_ingestion_failure_removes_partially_written_vectors(
    db: Session, settings: Settings, sample_pdf: Path
) -> None:
    document = add_document(db, settings, sample_pdf)

    class PartiallyFailingVectorStore(InMemoryVectorStore):
        def upsert(self, records) -> None:
            super().upsert(records)
            raise RuntimeError("simulated failure after vector write")

    vectors = PartiallyFailingVectorStore()
    IngestionService(settings, DeterministicEmbeddingProvider(), vectors).process(db, document.id)

    db.refresh(document)
    assert document.status == ProcessingStatus.FAILED
    assert vectors.records == {}
    assert db.scalar(select(func.count(DocumentPage.id))) == 0
    assert db.scalar(select(func.count(DocumentChunk.id))) == 0


def test_interrupted_ingestion_becomes_retryable(db: Session, settings: Settings) -> None:
    document = Document(
        original_name="interrupted.pdf",
        storage_name="interrupted.pdf",
        file_size=100,
        sha256="b" * 64,
        status=ProcessingStatus.PROCESSING,
    )
    db.add(document)
    db.flush()
    job = ProcessingJob(
        document_id=document.id,
        status=ProcessingStatus.PROCESSING,
        attempt=1,
    )
    db.add(job)
    db.commit()

    assert recover_interrupted_ingestion(db) == 1
    db.refresh(document)
    db.refresh(job)
    assert document.status == ProcessingStatus.FAILED
    assert "restart" in (document.processing_error or "")
    assert job.status == ProcessingStatus.FAILED


def test_background_worker_uses_persisted_chunk_settings(
    db: Session, settings: Settings, monkeypatch
) -> None:
    db.add(ApplicationSetting(key="chunk_size", value=json.dumps(333)))
    db.add(ApplicationSetting(key="chunk_overlap", value=json.dumps(33)))
    db.commit()
    captured: dict[str, Settings] = {}

    class CapturingIngestionService:
        def __init__(self, runtime: Settings, _embeddings: object, _vectors: object) -> None:
            captured["settings"] = runtime

        def process(self, _db: Session, _document_id: str) -> None:
            return None

    monkeypatch.setattr("app.workers.ingestion.SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr("app.workers.ingestion.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.workers.ingestion.get_embedding_provider", DeterministicEmbeddingProvider
    )
    monkeypatch.setattr("app.workers.ingestion.get_vector_store", InMemoryVectorStore)
    monkeypatch.setattr("app.workers.ingestion.IngestionService", CapturingIngestionService)

    process_document("document-id")

    assert captured["settings"].chunk_size == 333
    assert captured["settings"].chunk_overlap == 33
