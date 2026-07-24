from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
from app.rag.chat import COMPARE_MODE
from app.rag.grounding import INSUFFICIENT_EVIDENCE
from app.rag.verification import clear_verification_cache
from app.services.dependencies import get_vector_store
from app.services.embeddings import DeterministicEmbeddingProvider
from app.services.export import VERIFICATION_TRUNCATED_NOTE, slugify_title
from app.services.vector_store import VectorRecord


def seed_conversation(
    db: Session, title: str = "Pilot study findings"
) -> tuple[Conversation, DocumentChunk]:
    document = Document(
        original_name="trusted.pdf",
        storage_name="trusted.pdf",
        file_size=100,
        sha256="f" * 64,
        status=ProcessingStatus.READY,
        page_count=2,
        searchable_page_count=2,
    )
    conversation = Conversation(title=title)
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


def add_message(
    db: Session,
    conversation: Conversation,
    role: MessageRole,
    content: str,
    created_at: datetime,
    chunk: DocumentChunk | None = None,
    mode: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role=role,
        content=content,
        created_at=created_at,
        mode=mode,
    )
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


def seed_exchange(db: Session, conversation: Conversation, chunk: DocumentChunk) -> None:
    add_message(
        db,
        conversation,
        MessageRole.USER,
        "What was the result?",
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )
    add_message(
        db,
        conversation,
        MessageRole.ASSISTANT,
        "The verified result was 37 percent [trusted.pdf, p. 2]. "
        "The lunar colony was founded in 1999.",
        datetime(2026, 7, 24, 12, 1, tzinfo=UTC),
        chunk,
    )


def seed_vectors(chunk: DocumentChunk) -> None:
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


def test_markdown_export_structure(client: TestClient, db: Session) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    seed_vectors(chunk)
    seed_exchange(db, conversation, chunk)

    response = client.get(f"/api/v1/conversations/{conversation.id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="pilot-study-findings-')
    assert disposition.endswith('.md"')
    body = response.text
    assert body.startswith("# Pilot study findings\n")
    assert "GroundedPDF v" in body
    assert "## Q: What was the result?" in body
    assert "The verified result was 37 percent [trusted.pdf, p. 2]." in body
    assert "Verification: 1 of 2 claims supported" in body
    assert "### Sources" in body
    assert "1. [trusted.pdf, p. 2] — trusted.pdf, page 2" in body
    assert "   > The verified result was 37 percent." in body
    assert "## Generation settings" in body
    assert "- Provider: mock" in body
    assert "- Chunk size: 240 characters" in body
    assert "- Passages retrieved per question: 6" in body
    assert "Citations reference local documents" in body


def test_html_export_escapes_untrusted_content(client: TestClient, db: Session) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db, title="Quotes & <Escapes>")
    add_message(
        db,
        conversation,
        MessageRole.ASSISTANT,
        '<script>alert("x")</script> & other <b>markup</b>.',
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        chunk,
    )

    response = client.get(f"/api/v1/conversations/{conversation.id}/export?format=html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    disposition = response.headers["content-disposition"]
    assert 'filename="quotes-escapes-' in disposition
    assert disposition.endswith('.html"')
    body = response.text
    assert "<script>" not in body
    assert "<b>" not in body
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in body
    assert "<title>Quotes &amp; &lt;Escapes&gt;</title>" in body
    assert "trusted.pdf, page 2" in body


def test_compare_export_verification_ignores_refusal_and_heading_lines(
    client: TestClient, db: Session
) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    seed_vectors(chunk)
    add_message(
        db,
        conversation,
        MessageRole.USER,
        "Compare the findings",
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
    )
    add_message(
        db,
        conversation,
        MessageRole.ASSISTANT,
        "## trusted.pdf\n\n"
        "The verified result was 37 percent [trusted.pdf, p. 2].\n\n"
        "## missing.pdf\n\n"
        f"{INSUFFICIENT_EVIDENCE}",
        datetime(2026, 7, 24, 12, 1, tzinfo=UTC),
        chunk,
        mode=COMPARE_MODE,
    )

    response = client.get(f"/api/v1/conversations/{conversation.id}/export")

    assert response.status_code == 200
    # One claim total: the section headings and the refusal section are never
    # scored, so the summary reflects only the evidenced sentence.
    assert "Verification: 1 of 1 claim supported" in response.text


def test_html_export_renders_answer_markdown_structurally(client: TestClient, db: Session) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    add_message(
        db,
        conversation,
        MessageRole.ASSISTANT,
        "## alpha.pdf\n\n"
        "- First **bold** finding\n"
        "- Second `code` finding\n\n"
        "1. Ordered item\n\n"
        "> A quoted line\n\n"
        "<script>alert(1)</script> plain *text*.",
        datetime(2026, 7, 24, 12, 0, tzinfo=UTC),
        chunk,
    )

    response = client.get(f"/api/v1/conversations/{conversation.id}/export?format=html")

    assert response.status_code == 200
    body = response.text
    assert "<h3>alpha.pdf</h3>" in body
    assert "<ul><li>First <strong>bold</strong> finding</li>" in body
    assert "<li>Second <code>code</code> finding</li></ul>" in body
    assert "<ol><li>Ordered item</li></ol>" in body
    assert "<blockquote>A quoted line</blockquote>" in body
    assert "<em>text</em>" in body
    assert "## alpha.pdf" not in body
    assert "<script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_export_verifies_only_the_most_recent_answers(client: TestClient, db: Session) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    seed_vectors(chunk)
    base_time = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
    for index in range(52):
        add_message(
            db,
            conversation,
            MessageRole.ASSISTANT,
            f"The verified result was 37 percent in run {index}.",
            base_time + timedelta(minutes=index),
            chunk,
        )

    response = client.get(f"/api/v1/conversations/{conversation.id}/export")

    assert response.status_code == 200
    body = response.text
    assert body.count("Verification:") == 50
    assert VERIFICATION_TRUNCATED_NOTE in body


def test_export_survives_verification_failure(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    clear_verification_cache()
    conversation, chunk = seed_conversation(db)
    seed_exchange(db, conversation, chunk)

    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("vector store unavailable")

    monkeypatch.setattr("app.services.export.verify_message", broken)
    response = client.get(f"/api/v1/conversations/{conversation.id}/export")

    assert response.status_code == 200
    body = response.text
    assert "The verified result was 37 percent [trusted.pdf, p. 2]." in body
    assert "claims supported" not in body
    assert "Verification was unavailable when this export was generated" in body


def test_export_empty_conversation_is_header_only(client: TestClient, db: Session) -> None:
    conversation = Conversation(title="Untitled research")
    db.add(conversation)
    db.commit()

    response = client.get(f"/api/v1/conversations/{conversation.id}/export")

    assert response.status_code == 200
    body = response.text
    assert body.startswith("# Untitled research\n")
    assert "## Q:" not in body
    assert "### Sources" not in body
    assert "## Generation settings" in body


def test_export_unknown_conversation_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/conversations/unknown/export")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


def test_export_rejects_unknown_format(client: TestClient, db: Session) -> None:
    conversation, _ = seed_conversation(db)

    response = client.get(f"/api/v1/conversations/{conversation.id}/export?format=pdf")

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Pilot study findings", "pilot-study-findings"),
        ("  Q3 -- Report / Findings!  ", "q3-report-findings"),
        ("Ω ???", "conversation"),
        ("", "conversation"),
        ("a" * 300, "a" * 80),
    ],
)
def test_slugify_title(title: str, expected: str) -> None:
    assert slugify_title(title) == expected
