from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import (
    Citation,
    Conversation,
    ConversationDocument,
    Document,
    DocumentChunk,
    DocumentPage,
    Message,
    MessageRole,
    ProcessingStatus,
)
from app.rag.grounding import INSUFFICIENT_EVIDENCE
from app.rag.verification import clear_verification_cache, split_sentences, verify_message
from app.services.dependencies import get_vector_store
from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.vector_store import InMemoryVectorStore, VectorRecord


def test_splitter_protects_abbreviations_and_decimals() -> None:
    text = (
        "Dr. Smith measured a 3.5 percent margin. "
        "Results improved elsewhere, e.g. Berlin doubled output. "
        "The final gain was 37 percent."
    )
    assert split_sentences(text) == [
        "Dr. Smith measured a 3.5 percent margin.",
        "Results improved elsewhere, e.g. Berlin doubled output.",
        "The final gain was 37 percent.",
    ]


def test_splitter_keeps_citation_markers_and_strips_markdown_noise() -> None:
    text = (
        "The gain was 37 percent [sample.pdf, p. 2]. A second claim follows.\n"
        "- First finding. Second finding.\n"
        "## Heading claim."
    )
    assert split_sentences(text) == [
        "The gain was 37 percent [sample.pdf, p. 2].",
        "A second claim follows.",
        "First finding.",
        "Second finding.",
        "Heading claim.",
    ]


def seed_conversation(db: Session) -> tuple[Conversation, DocumentChunk]:
    document = Document(
        original_name="trusted.pdf",
        storage_name="trusted.pdf",
        file_size=100,
        sha256="e" * 64,
        status=ProcessingStatus.READY,
        page_count=2,
        searchable_page_count=2,
    )
    conversation = Conversation(title="Verification scope")
    db.add_all([document, conversation])
    db.flush()
    page = DocumentPage(
        document_id=document.id,
        page_number=2,
        raw_text="The verified result was 37 percent.",
        normalized_text="The verified result was 37 percent.",
        is_searchable=True,
        character_count=35,
    )
    db.add(page)
    db.flush()
    chunk = DocumentChunk(
        document_id=document.id,
        page_id=page.id,
        page_number=2,
        chunk_index=0,
        raw_text=page.raw_text,
        normalized_text=page.normalized_text,
        start_offset=0,
        end_offset=len(page.normalized_text),
        embedding_id=f"{document.id}:2:0",
    )
    db.add(chunk)
    db.add(ConversationDocument(conversation_id=conversation.id, document_id=document.id))
    db.commit()
    return conversation, chunk


def add_assistant_message(
    db: Session, conversation: Conversation, content: str, chunk: DocumentChunk | None = None
) -> Message:
    message = Message(conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=content)
    db.add(message)
    db.flush()
    if chunk is not None:
        db.add(
            Citation(
                message_id=message.id,
                document_id=chunk.document_id,
                document_name="trusted.pdf",
                page_number=chunk.page_number,
                excerpt=chunk.normalized_text,
                retrieval_score=0.9,
                ordinal=1,
            )
        )
    db.commit()
    db.refresh(message)
    return message


def test_sentence_verdicts_use_relational_sources(db: Session, settings: Settings) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert(
        [
            VectorRecord(
                id=chunk.embedding_id,
                text=chunk.normalized_text,
                embedding=provider.embed([chunk.normalized_text])[0],
                metadata={"document_id": chunk.document_id, "document_name": "tampered.pdf"},
            )
        ]
    )
    message = add_assistant_message(
        db,
        conversation,
        "The verified result was 37 percent [trusted.pdf, p. 2]. "
        "The lunar colony was founded in 1999.",
        chunk,
    )

    result = verify_message(db, settings, provider, store, message)

    assert [sentence.verdict for sentence in result.sentences] == ["supported", "unsupported"]
    supported, unsupported = result.sentences
    assert supported.score >= settings.verification_supported_score
    assert supported.source is not None
    # Source metadata is rebuilt from relational records, not vector metadata.
    assert supported.source.document_name == "trusted.pdf"
    assert supported.source.page_number == 2
    assert supported.source.excerpt == "The verified result was 37 percent."
    assert unsupported.source is None
    assert unsupported.score < settings.verification_weak_score


def test_verification_results_are_cached_per_message(db: Session, settings: Settings) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    provider = DeterministicEmbeddingProvider()
    store = InMemoryVectorStore()
    store.upsert(
        [
            VectorRecord(
                id=chunk.embedding_id,
                text=chunk.normalized_text,
                embedding=provider.embed([chunk.normalized_text])[0],
                metadata={"document_id": chunk.document_id},
            )
        ]
    )
    message = add_assistant_message(db, conversation, "The verified result was 37 percent.", chunk)

    first = verify_message(db, settings, provider, store, message)
    store.delete_document(chunk.document_id)
    second = verify_message(db, settings, provider, store, message)

    assert second is first


def test_verify_endpoint_shape_and_missing_messages(client: TestClient, db: Session) -> None:
    conversation, chunk = seed_conversation(db)
    provider = DeterministicEmbeddingProvider()
    get_vector_store().upsert(
        [
            VectorRecord(
                id=chunk.embedding_id,
                text=chunk.normalized_text,
                embedding=provider.embed([chunk.normalized_text])[0],
                metadata={"document_id": chunk.document_id},
            )
        ]
    )
    assistant = add_assistant_message(
        db, conversation, "The verified result was 37 percent [trusted.pdf, p. 2].", chunk
    )
    user = Message(
        conversation_id=conversation.id, role=MessageRole.USER, content="What was the result?"
    )
    db.add(user)
    db.commit()

    response = client.get(f"/api/v1/conversations/{conversation.id}/messages/{assistant.id}/verify")
    assert response.status_code == 200
    payload = response.json()
    assert payload["message_id"] == assistant.id
    assert payload["generated_at"]
    assert payload["sentences"][0]["verdict"] == "supported"
    assert payload["sentences"][0]["source"]["document_id"] == chunk.document_id
    assert payload["sentences"][0]["source"]["page_number"] == 2

    for missing in (
        f"/api/v1/conversations/{conversation.id}/messages/{user.id}/verify",
        f"/api/v1/conversations/{conversation.id}/messages/unknown/verify",
        f"/api/v1/conversations/unknown/messages/{assistant.id}/verify",
    ):
        not_found = client.get(missing)
        assert not_found.status_code == 404
        assert not_found.json()["error"]["code"] == "message_not_found"


def test_verify_insufficient_evidence_answer_is_empty(client: TestClient, db: Session) -> None:
    conversation, _ = seed_conversation(db)
    message = add_assistant_message(db, conversation, INSUFFICIENT_EVIDENCE)

    response = client.get(f"/api/v1/conversations/{conversation.id}/messages/{message.id}/verify")

    assert response.status_code == 200
    assert response.json()["sentences"] == []
