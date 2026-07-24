from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ProviderUnavailableError
from app.models.entities import (
    Conversation,
    ConversationDocument,
    Document,
    DocumentChunk,
    DocumentPage,
    Message,
    MessageRole,
    ProcessingStatus,
)
from app.rag.chat import ChatService
from app.rag.grounding import (
    GENERATION_FAILED_MESSAGE,
    INSUFFICIENT_EVIDENCE,
    GroundedCitation,
)
from app.services.vector_store import VectorMatch


class StubRetriever:
    def __init__(self, matches: list[VectorMatch]) -> None:
        self.matches = matches
        self.scoped_document_ids: list[str] = []

    def retrieve(self, _question: str, document_ids: list[str]) -> list[VectorMatch]:
        self.scoped_document_ids = document_ids
        return self.matches


class RecordingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, _system_prompt: str, _user_prompt: str) -> AsyncIterator[str]:
        self.calls += 1
        yield "answer"

    async def health(self) -> tuple[bool, str | None]:
        return True, None


def seed_conversation(db: Session) -> tuple[Conversation, DocumentChunk]:
    selected = Document(
        original_name="trusted.pdf",
        storage_name="trusted.pdf",
        file_size=100,
        sha256="c" * 64,
        status=ProcessingStatus.READY,
        page_count=3,
        searchable_page_count=3,
    )
    unselected = Document(
        original_name="unselected.pdf",
        storage_name="unselected.pdf",
        file_size=100,
        sha256="d" * 64,
        status=ProcessingStatus.READY,
        page_count=1,
        searchable_page_count=1,
    )
    conversation = Conversation(title="Trusted scope")
    db.add_all([selected, unselected, conversation])
    db.flush()
    page = DocumentPage(
        document_id=selected.id,
        page_number=2,
        raw_text="The verified result was 37 percent.",
        normalized_text="The verified result was 37 percent.",
        is_searchable=True,
        character_count=35,
    )
    db.add(page)
    db.flush()
    chunk = DocumentChunk(
        document_id=selected.id,
        page_id=page.id,
        page_number=2,
        chunk_index=0,
        raw_text=page.raw_text,
        normalized_text=page.normalized_text,
        start_offset=0,
        end_offset=len(page.normalized_text),
        embedding_id=f"{selected.id}:2:0",
    )
    db.add(chunk)
    db.add(ConversationDocument(conversation_id=conversation.id, document_id=selected.id))
    db.commit()
    return conversation, chunk


def test_chat_revalidates_retrieval_metadata_against_relational_chunks(
    db: Session, settings: Settings
) -> None:
    conversation, chunk = seed_conversation(db)
    retriever = StubRetriever(
        [
            VectorMatch(
                id=chunk.embedding_id,
                text="Tampered vector text",
                metadata={
                    "document_id": chunk.document_id,
                    "document_name": "invented.pdf",
                    "page_number": 999,
                },
                score=0.91,
            )
        ]
    )
    service = ChatService(settings, retriever, RecordingProvider())  # type: ignore[arg-type]
    previous_updated_at = conversation.updated_at

    _, citations, prompt = service.prepare(db, conversation.id, "What was the result?")
    db.refresh(conversation)

    assert retriever.scoped_document_ids == [chunk.document_id]
    assert citations[0].document_name == "trusted.pdf"
    assert citations[0].page_number == 2
    assert "The verified result was 37 percent." in (prompt or "")
    assert "Tampered vector text" not in (prompt or "")
    assert conversation.updated_at > previous_updated_at


@pytest.mark.asyncio
async def test_stale_vector_record_returns_insufficient_evidence_without_provider(
    db: Session, settings: Settings
) -> None:
    conversation, chunk = seed_conversation(db)
    retriever = StubRetriever(
        [
            VectorMatch(
                id="missing-vector-record",
                text="Untrusted stale evidence",
                metadata={
                    "document_id": chunk.document_id,
                    "document_name": "fake.pdf",
                    "page_number": 8,
                },
                score=0.99,
            )
        ]
    )
    provider = RecordingProvider()
    service = ChatService(settings, retriever, provider)  # type: ignore[arg-type]

    _, citations, prompt = service.prepare(db, conversation.id, "Unsupported question")
    answer = "".join([token async for token in service.tokens(prompt)])

    assert citations == []
    assert prompt is None
    assert answer == INSUFFICIENT_EVIDENCE
    assert provider.calls == 0


def test_empty_grounded_provider_answer_is_rejected() -> None:
    citations = [
        GroundedCitation(
            document_id="document",
            document_name="source.pdf",
            page_number=1,
            excerpt="Evidence",
            score=0.9,
            ordinal=1,
        )
    ]

    with pytest.raises(ProviderUnavailableError, match="empty answer"):
        ChatService.finalize_answer("   ", citations)


def test_retrieval_failure_rolls_back_the_user_message(db: Session, settings: Settings) -> None:
    """A retrieval crash must not leave an orphaned question in the conversation."""
    conversation, _chunk = seed_conversation(db)

    class FailingRetriever:
        def retrieve(self, _question: str, _document_ids: list[str]) -> list[VectorMatch]:
            raise RuntimeError("vector store offline")

    service = ChatService(settings, FailingRetriever(), RecordingProvider())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="vector store offline"):
        service.prepare(db, conversation.id, "What was the result?")

    assert db.scalar(select(func.count(Message.id))) == 0


def test_failed_generation_persists_user_message_and_placeholder_answer(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-stream route: a provider failure leaves a question plus a failed-answer placeholder."""
    conversation = Conversation(title="Failing provider")
    db.add(conversation)
    db.commit()

    class FailingService:
        def prepare(self, session: Session, conversation_id: str, question: str):
            message = Message(
                conversation_id=conversation_id, role=MessageRole.USER, content=question
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message, [], "prompt"

        async def tokens(self, _prompt: str):
            if False:
                yield ""
            raise ProviderUnavailableError("Provider offline for test")

    monkeypatch.setattr(
        "app.api.routes.conversations.make_chat_service", lambda _db, _base: FailingService()
    )

    response = client.post(
        f"/api/v1/conversations/{conversation.id}/messages", json={"question": "What happened?"}
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    )
    assert [message.role for message in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[0].content == "What happened?"
    assert messages[1].content == GENERATION_FAILED_MESSAGE
    assert messages[1].mode is None
    assert messages[1].citations == []


def test_unexpected_stream_failure_returns_typed_sse_error(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = Conversation(title="Broken stream")
    db.add(conversation)
    db.commit()

    class BrokenService:
        def prepare(self, session: Session, conversation_id: str, question: str):
            message = Message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=question,
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message, [], "prompt"

        async def tokens(self, _prompt: str):
            if False:
                yield ""
            raise RuntimeError("private provider details")

    monkeypatch.setattr(
        "app.api.routes.conversations.make_chat_service", lambda _db, _base: BrokenService()
    )

    response = client.post(
        f"/api/v1/conversations/{conversation.id}/messages/stream",
        json={"question": "What happened?"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert '"code": "internal_error"' in response.text
    assert '"status": 500' in response.text
    assert "private provider details" not in response.text
    # The question is never orphaned: a fixed failed-answer placeholder is
    # persisted best-effort alongside the committed user message.
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    )
    assert [message.role for message in messages] == [MessageRole.USER, MessageRole.ASSISTANT]
    assert messages[1].content == GENERATION_FAILED_MESSAGE
    assert messages[1].citations == []
