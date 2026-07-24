from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import GroundedPdfError
from app.models.entities import (
    Conversation,
    ConversationDocument,
    Document,
    DocumentChunk,
    DocumentPage,
    ProcessingStatus,
)
from app.rag.chat import ChatService
from app.rag.grounding import INSUFFICIENT_EVIDENCE
from app.services.dependencies import get_vector_store
from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.vector_store import VectorMatch, VectorRecord


class ScopedStubRetriever:
    """Returns canned matches per document and records each retrieval scope."""

    def __init__(self, matches_by_document: dict[str, list[VectorMatch]]) -> None:
        self.matches_by_document = matches_by_document
        self.scopes: list[list[str]] = []

    def retrieve(self, _question: str, document_ids: list[str]) -> list[VectorMatch]:
        self.scopes.append(list(document_ids))
        return [
            match
            for document_id in document_ids
            for match in self.matches_by_document.get(document_id, [])
        ]


class RecordingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, _system_prompt: str, _user_prompt: str) -> AsyncIterator[str]:
        self.calls += 1
        yield "answer"

    async def health(self) -> tuple[bool, str | None]:
        return True, None


def seed_document(
    db: Session,
    name: str,
    text: str,
    status: ProcessingStatus = ProcessingStatus.READY,
) -> DocumentChunk:
    document = Document(
        original_name=name,
        storage_name=f"{name}.stored",
        file_size=100,
        sha256=name.ljust(64, "0")[:64],
        status=status,
        page_count=1,
        searchable_page_count=1,
    )
    db.add(document)
    db.flush()
    page = DocumentPage(
        document_id=document.id,
        page_number=2,
        raw_text=text,
        normalized_text=text,
        is_searchable=True,
        character_count=len(text),
    )
    db.add(page)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        page_id=page.id,
        page_number=2,
        chunk_index=0,
        raw_text=text,
        normalized_text=text,
        start_offset=0,
        end_offset=len(text),
        embedding_id=f"{document.id}:2:0",
    )
    db.add(chunk)
    db.commit()
    return chunk


def link_documents(db: Session, conversation: Conversation, document_ids: list[str]) -> None:
    for document_id in document_ids:
        db.add(ConversationDocument(conversation_id=conversation.id, document_id=document_id))
    db.commit()


def match_for(chunk: DocumentChunk, name: str) -> VectorMatch:
    return VectorMatch(
        id=chunk.embedding_id,
        text=chunk.normalized_text,
        metadata={
            "document_id": chunk.document_id,
            "document_name": name,
            "page_number": chunk.page_number,
        },
        score=0.9,
    )


@pytest.mark.asyncio
async def test_compare_answers_per_document_and_refuses_without_evidence(
    db: Session, settings: Settings
) -> None:
    evidenced = seed_document(db, "alpha.pdf", "The measured efficiency gain was 37 percent.")
    empty = seed_document(db, "beta.pdf", "Unrelated content that is never indexed.")
    conversation = Conversation(title="Compare")
    db.add(conversation)
    db.flush()
    link_documents(db, conversation, [evidenced.document_id, empty.document_id])

    retriever = ScopedStubRetriever({evidenced.document_id: [match_for(evidenced, "alpha.pdf")]})
    provider = RecordingProvider()
    service = ChatService(settings, retriever, provider)  # type: ignore[arg-type]

    user_message, sections = service.prepare_compare(
        db, conversation.id, "What efficiency gain was measured?"
    )

    # Retrieval is scoped to one document at a time, ordered by display name.
    assert retriever.scopes == [[evidenced.document_id], [empty.document_id]]
    assert user_message.mode == "compare"
    assert [section.document_name for section in sections] == ["alpha.pdf", "beta.pdf"]
    assert {citation.document_id for citation in sections[0].citations} == {evidenced.document_id}
    assert sections[1].citations == []
    assert sections[1].prompt is None

    streamed = "".join([token async for token in service.compare_events(sections)])

    # Only the evidencing document reached the provider.
    assert provider.calls == 1
    assert sections[1].answer == INSUFFICIENT_EVIDENCE
    assert "[alpha.pdf, p. 2]" in sections[0].answer
    assert "## alpha.pdf" in streamed
    assert "## beta.pdf" in streamed
    assert INSUFFICIENT_EVIDENCE in streamed

    persisted = ChatService.persist_compare_answer(db, conversation.id, sections)

    assert persisted.mode == "compare"
    assert persisted.content.startswith("## alpha.pdf\n\n")
    assert f"## beta.pdf\n\n{INSUFFICIENT_EVIDENCE}" in persisted.content
    assert {citation.document_id for citation in persisted.citations} == {evidenced.document_id}


def test_compare_citation_ordinals_are_unique_across_sections(
    db: Session, settings: Settings
) -> None:
    first = seed_document(db, "alpha.pdf", "The measured efficiency gain was 37 percent.")
    second = seed_document(db, "beta.pdf", "The control group efficiency gain was 12 percent.")
    conversation = Conversation(title="Compare")
    db.add(conversation)
    db.flush()
    link_documents(db, conversation, [first.document_id, second.document_id])

    retriever = ScopedStubRetriever(
        {
            first.document_id: [match_for(first, "alpha.pdf")],
            second.document_id: [match_for(second, "beta.pdf")],
        }
    )
    service = ChatService(settings, retriever, RecordingProvider())  # type: ignore[arg-type]

    _, sections = service.prepare_compare(db, conversation.id, "What was the efficiency gain?")
    for section in sections:
        section.answer = f"Answer. {section.citations[0].marker}"
    persisted = ChatService.persist_compare_answer(db, conversation.id, sections)

    assert [citation.ordinal for citation in persisted.citations] == [1, 2]
    assert [citation.document_name for citation in persisted.citations] == [
        "alpha.pdf",
        "beta.pdf",
    ]


def test_compare_requires_at_least_two_ready_documents(db: Session, settings: Settings) -> None:
    ready = seed_document(db, "alpha.pdf", "Some indexed content.")
    processing = seed_document(
        db, "beta.pdf", "Still processing.", status=ProcessingStatus.PROCESSING
    )
    conversation = Conversation(title="Compare")
    db.add(conversation)
    db.flush()
    link_documents(db, conversation, [ready.document_id, processing.document_id])

    service = ChatService(settings, ScopedStubRetriever({}), RecordingProvider())  # type: ignore[arg-type]

    with pytest.raises(GroundedPdfError) as excinfo:
        service.prepare_compare(db, conversation.id, "Compare these")
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "compare_needs_two_documents"


def test_compare_caps_the_number_of_documents(db: Session, settings: Settings) -> None:
    chunks = [seed_document(db, f"document-{index}.pdf", f"Content {index}.") for index in range(5)]
    conversation = Conversation(title="Compare")
    db.add(conversation)
    db.flush()
    link_documents(db, conversation, [chunk.document_id for chunk in chunks])

    service = ChatService(settings, ScopedStubRetriever({}), RecordingProvider())  # type: ignore[arg-type]

    with pytest.raises(GroundedPdfError) as excinfo:
        service.prepare_compare(db, conversation.id, "Compare these")
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "compare_too_many_documents"


def test_compare_stream_emits_sections_over_the_existing_sse_protocol(
    client: TestClient, db: Session
) -> None:
    provider = DeterministicEmbeddingProvider()
    evidenced = seed_document(db, "alpha.pdf", "The measured efficiency gain was 37 percent.")
    empty = seed_document(db, "beta.pdf", "Nothing here was indexed.")
    get_vector_store().upsert(
        [
            VectorRecord(
                id=evidenced.embedding_id,
                text=evidenced.normalized_text,
                embedding=provider.embed([evidenced.normalized_text])[0],
                metadata={
                    "document_id": evidenced.document_id,
                    "document_name": "alpha.pdf",
                },
            )
        ]
    )
    conversation = Conversation(title="Compare")
    db.add(conversation)
    db.flush()
    link_documents(db, conversation, [evidenced.document_id, empty.document_id])

    response = client.post(
        f"/api/v1/conversations/{conversation.id}/messages/stream",
        json={"question": "What efficiency gain was measured?", "mode": "compare"},
    )

    assert response.status_code == 200
    assert "event: metadata" in response.text
    assert "event: done" in response.text
    assert "## alpha.pdf" in response.text
    assert "## beta.pdf" in response.text
    assert INSUFFICIENT_EVIDENCE in response.text
    assert '"mode": "compare"' in response.text
    # Citations come only from the evidencing document.
    assert '"document_name": "beta.pdf"' not in response.text


def test_compare_rejects_fewer_than_two_ready_documents_over_http(
    client: TestClient, db: Session
) -> None:
    only = seed_document(db, "alpha.pdf", "Some indexed content.")
    conversation = Conversation(title="Compare")
    db.add(conversation)
    db.flush()
    link_documents(db, conversation, [only.document_id])

    response = client.post(
        f"/api/v1/conversations/{conversation.id}/messages/stream",
        json={"question": "Compare these documents", "mode": "compare"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "compare_needs_two_documents"
