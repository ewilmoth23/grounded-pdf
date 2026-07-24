from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace

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
    StreamingCitationFilter,
    build_citations,
    build_user_prompt,
    ensure_inline_citation,
    select_cited_matches,
)
from app.rag.retrieval import Retriever
from app.services.vector_store import VectorMatch

logger = logging.getLogger(__name__)

COMPARE_MODE = "compare"
COMPARE_DOCUMENT_LIMIT = 4


@dataclass
class CompareSection:
    """One document's share of a compare answer.

    ``prompt`` is None when retrieval found no admissible evidence for the
    document; that section gets the fixed refusal without a provider call.
    ``answer`` is filled with the finalized section text during streaming.
    """

    document_id: str
    document_name: str
    citations: list[GroundedCitation] = field(default_factory=list)
    prompt: str | None = None
    answer: str = ""


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

    def prepare_compare(
        self, db: Session, conversation_id: str, question: str
    ) -> tuple[Message, list[CompareSection]]:
        """Persist the compare question and run retrieval separately per document."""
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
        ready_by_id = {
            document.id: document
            for document in db.scalars(
                select(Document).where(
                    Document.id.in_(selected_ids), Document.status == ProcessingStatus.READY
                )
            )
        }
        # Selection order is not persisted, so order sections deterministically
        # by display name (tiebreak on id) for stable, user-predictable output.
        ordered = sorted(
            (
                ready_by_id[document_id]
                for document_id in selected_ids
                if document_id in ready_by_id
            ),
            key=lambda document: ((document.title or document.original_name).lower(), document.id),
        )
        if len(ordered) < 2:
            raise GroundedPdfError(
                "Compare mode needs at least two ready documents selected.",
                code="compare_needs_two_documents",
                status_code=422,
            )
        if len(ordered) > COMPARE_DOCUMENT_LIMIT:
            raise GroundedPdfError(
                f"Compare mode supports up to {COMPARE_DOCUMENT_LIMIT} documents."
                " Deselect some documents and retry.",
                code="compare_too_many_documents",
                status_code=422,
            )
        user_message = Message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=question.strip(),
            mode=COMPARE_MODE,
        )
        db.add(user_message)
        conversation.updated_at = utc_now()
        db.commit()
        db.refresh(user_message)
        sections: list[CompareSection] = []
        next_ordinal = 1
        for document in ordered:
            matches = self._validated_matches(
                db, self.retriever.retrieve(question, [document.id]), [document.id]
            )
            section = CompareSection(document_id=document.id, document_name=document.original_name)
            if matches:
                section.citations = [
                    replace(citation, ordinal=next_ordinal + index)
                    for index, citation in enumerate(
                        build_citations(matches, maximum=self.settings.retrieval_count)
                    )
                ]
                next_ordinal += len(section.citations)
                section.prompt = build_user_prompt(
                    question, select_cited_matches(matches, section.citations)
                )
            sections.append(section)
        return user_message, sections

    async def compare_events(self, sections: list[CompareSection]) -> AsyncIterator[str]:
        """Yield the compare answer as safe tokens, one grounded section per document.

        Each section streams through its own citation filter restricted to that
        document's markers. Sections without evidence yield the fixed refusal and
        never reach the provider. The finalized text is stored on each section.
        """
        for index, section in enumerate(sections):
            heading = f"## {section.document_name}\n\n"
            if index:
                heading = f"\n\n{heading}"
            yield heading
            if section.prompt is None:
                section.answer = INSUFFICIENT_EVIDENCE
                yield INSUFFICIENT_EVIDENCE
                continue
            answer = ""
            citation_filter = StreamingCitationFilter(section.citations)
            async for token in self.tokens(section.prompt):
                safe_token = citation_filter.feed(token)
                if safe_token:
                    answer += safe_token
                    yield safe_token
            trailing_text = citation_filter.finish()
            if trailing_text:
                answer += trailing_text
                yield trailing_text
            finalized = self.finalize_answer(answer, section.citations)
            if finalized != answer and finalized.startswith(answer):
                yield finalized[len(answer) :]
            section.answer = finalized

    @staticmethod
    def compose_compare_content(sections: list[CompareSection]) -> str:
        return "\n\n".join(
            f"## {section.document_name}\n\n{section.answer}" for section in sections
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
        return ChatService._persist_message(db, conversation_id, final_answer, citations, None)

    @staticmethod
    def persist_compare_answer(
        db: Session, conversation_id: str, sections: list[CompareSection]
    ) -> Message:
        """Persist the composed per-document sections as one assistant message.

        Sections are already finalized individually (each evidencing section
        carries its own filtered inline markers), so the composed content is
        persisted as-is with the union of per-document citations.
        """
        citations = [citation for section in sections for citation in section.citations]
        content = ChatService.compose_compare_content(sections)
        return ChatService._persist_message(db, conversation_id, content, citations, COMPARE_MODE)

    @staticmethod
    def _persist_message(
        db: Session,
        conversation_id: str,
        content: str,
        citations: list[GroundedCitation],
        mode: str | None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=content,
            mode=mode,
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
