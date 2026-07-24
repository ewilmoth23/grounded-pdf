from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import Settings
from app.core.exceptions import GroundedPdfError, ProviderUnavailableError
from app.models.entities import (
    Citation,
    Conversation,
    Document,
    DocumentChunk,
    Message,
    MessageRole,
    ProcessingStatus,
    utc_now,
)
from app.providers.base import ChatProvider
from app.rag.grounding import (
    INSUFFICIENT_EVIDENCE,
    SYSTEM_PROMPT,
    GroundedCitation,
    build_citations,
    build_user_prompt,
    ensure_inline_citation,
    select_cited_matches,
)
from app.rag.retrieval import Retriever
from app.services.vector_store import VectorMatch

logger = logging.getLogger(__name__)


def validate_matches(
    db: Session, matches: list[VectorMatch], document_ids: list[str]
) -> list[VectorMatch]:
    """Rebuild retrieved evidence from relational chunks before trusting it."""
    if not matches:
        return []
    chunks = db.scalars(
        select(DocumentChunk)
        .options(joinedload(DocumentChunk.document))
        .where(
            DocumentChunk.embedding_id.in_([match.id for match in matches]),
            DocumentChunk.document_id.in_(document_ids),
        )
    )
    by_embedding_id = {chunk.embedding_id: chunk for chunk in chunks}
    validated: list[VectorMatch] = []
    for match in matches:
        chunk = by_embedding_id.get(match.id)
        if chunk is None:
            continue
        validated.append(
            VectorMatch(
                id=chunk.embedding_id,
                text=chunk.normalized_text,
                metadata={
                    "document_id": chunk.document_id,
                    "document_name": chunk.document.original_name,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "chunk_id": chunk.id,
                },
                score=match.score,
            )
        )
    return validated


class ChatService:
    def __init__(self, settings: Settings, retriever: Retriever, provider: ChatProvider) -> None:
        self.settings = settings
        self.retriever = retriever
        self.provider = provider

    def prepare(
        self, db: Session, conversation_id: str, question: str
    ) -> tuple[Message, list[GroundedCitation], str | None]:
        conversation = db.scalar(
            select(Conversation)
            .options(selectinload(Conversation.document_links))
            .where(Conversation.id == conversation_id)
        )
        if conversation is None:
            raise GroundedPdfError(
                "Conversation not found", code="conversation_not_found", status_code=404
            )
        selected_ids = [link.document_id for link in conversation.document_links]
        ready_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.id.in_(selected_ids), Document.status == ProcessingStatus.READY
                )
            )
        )
        if not ready_ids:
            raise GroundedPdfError(
                "Select at least one processed document before asking a question",
                code="no_ready_documents",
                status_code=422,
            )
        user_message = Message(
            conversation_id=conversation_id, role=MessageRole.USER, content=question.strip()
        )
        db.add(user_message)
        conversation.updated_at = utc_now()
        db.commit()
        db.refresh(user_message)
        matches = self._validated_matches(
            db, self.retriever.retrieve(question, ready_ids), ready_ids
        )
        if not matches:
            return user_message, [], None
        citations = build_citations(matches, maximum=self.settings.retrieval_count)
        return (
            user_message,
            citations,
            build_user_prompt(question, select_cited_matches(matches, citations)),
        )

    @staticmethod
    def _validated_matches(
        db: Session, matches: list[VectorMatch], ready_ids: list[str]
    ) -> list[VectorMatch]:
        """Rebuild retrieved evidence from relational chunks before prompting or citing it."""
        return validate_matches(db, matches, ready_ids)

    async def tokens(self, prompt: str | None) -> AsyncIterator[str]:
        if prompt is None:
            yield INSUFFICIENT_EVIDENCE
            return
        started = time.monotonic()
        async for token in self.provider.stream(SYSTEM_PROMPT, prompt):
            yield token
        logger.info(
            "model_request_completed",
            extra={"duration_ms": round((time.monotonic() - started) * 1000)},
        )

    @staticmethod
    def finalize_answer(answer: str, citations: list[GroundedCitation]) -> str:
        if citations and not answer.strip():
            raise ProviderUnavailableError(
                "The configured model provider returned an empty answer. Check the model and retry."
            )
        return ensure_inline_citation(answer, citations)

    @staticmethod
    def persist_answer(
        db: Session,
        conversation_id: str,
        answer: str,
        citations: list[GroundedCitation],
    ) -> Message:
        final_answer = ChatService.finalize_answer(answer, citations)
        message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final_answer,
        )
        db.add(message)
        db.flush()
        for citation in citations:
            db.add(
                Citation(
                    message_id=message.id,
                    document_id=citation.document_id,
                    document_name=citation.document_name,
                    page_number=citation.page_number,
                    excerpt=citation.excerpt,
                    retrieval_score=citation.score,
                    ordinal=citation.ordinal,
                )
            )
        db.commit()
        persisted = db.scalar(
            select(Message).options(selectinload(Message.citations)).where(Message.id == message.id)
        )
        if persisted is None:
            raise RuntimeError("Persisted assistant message could not be reloaded")
        return persisted
