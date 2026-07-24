from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings
from app.core.exceptions import GroundedPdfError
from app.db.session import get_db
from app.models.entities import (
    Conversation,
    ConversationDocument,
    Document,
    Message,
    MessageRole,
    utc_now,
)
from app.providers.factory import create_chat_provider
from app.rag.chat import ChatService, CompareSection
from app.rag.grounding import StreamingCitationFilter
from app.rag.retrieval import Retriever
from app.rag.verification import VerificationResult, verify_message
from app.schemas.common import DeleteResponse
from app.schemas.conversations import (
    AnswerResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationDocumentsUpdate,
    ConversationRename,
    ConversationResponse,
    MessageResponse,
    QuestionRequest,
    VerificationResponse,
    VerificationSentenceResponse,
    VerificationSourceResponse,
)
from app.services.dependencies import get_embedding_provider, get_vector_store
from app.services.export import ConversationExport, ExportFormat, build_export
from app.services.settings import effective_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def require_conversation(db: Session, conversation_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.document_links), selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    if conversation is None:
        raise GroundedPdfError(
            "Conversation not found", code="conversation_not_found", status_code=404
        )
    return conversation


def to_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        document_ids=[link.document_id for link in conversation.document_links],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def make_chat_service(db: Session, base: Settings) -> ChatService:
    runtime = effective_settings(db, base)
    retriever = Retriever(runtime, get_embedding_provider(), get_vector_store())
    return ChatService(runtime, retriever, create_chat_provider(runtime))


def set_documents(db: Session, conversation: Conversation, document_ids: list[str]) -> None:
    unique_ids = list(dict.fromkeys(document_ids))
    existing_ids = set(
        db.scalars(select(Document.id).where(Document.id.in_(unique_ids))) if unique_ids else []
    )
    missing = set(unique_ids) - existing_ids
    if missing:
        raise GroundedPdfError(
            "One or more selected documents do not exist",
            code="document_not_found",
            status_code=404,
        )
    conversation.document_links.clear()
    conversation.document_links.extend(
        ConversationDocument(document_id=document_id) for document_id in unique_ids
    )
    conversation.updated_at = utc_now()


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(
    payload: ConversationCreate, db: Session = Depends(get_db)
) -> ConversationResponse:
    conversation = Conversation(title=payload.title.strip())
    db.add(conversation)
    db.flush()
    set_documents(db, conversation, payload.document_ids)
    db.commit()
    db.refresh(conversation)
    return to_response(conversation)


@router.get("", response_model=list[ConversationResponse])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationResponse]:
    conversations = db.scalars(
        select(Conversation)
        .options(selectinload(Conversation.document_links))
        .order_by(Conversation.updated_at.desc())
    )
    return [to_response(conversation) for conversation in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db)
) -> ConversationDetailResponse:
    conversation = db.scalar(
        select(Conversation)
        .options(
            selectinload(Conversation.document_links),
            selectinload(Conversation.messages).selectinload(Message.citations),
        )
        .where(Conversation.id == conversation_id)
    )
    if conversation is None:
        raise GroundedPdfError(
            "Conversation not found", code="conversation_not_found", status_code=404
        )
    return ConversationDetailResponse(
        **to_response(conversation).model_dump(),
        messages=[MessageResponse.model_validate(message) for message in conversation.messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: str, payload: ConversationRename, db: Session = Depends(get_db)
) -> ConversationResponse:
    conversation = require_conversation(db, conversation_id)
    conversation.title = payload.title.strip()
    db.commit()
    return to_response(conversation)


@router.put("/{conversation_id}/documents", response_model=ConversationResponse)
def update_conversation_documents(
    conversation_id: str,
    payload: ConversationDocumentsUpdate,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conversation = require_conversation(db, conversation_id)
    set_documents(db, conversation, payload.document_ids)
    db.commit()
    return to_response(conversation)


@router.delete("/{conversation_id}", response_model=DeleteResponse)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> DeleteResponse:
    conversation = require_conversation(db, conversation_id)
    db.delete(conversation)
    db.commit()
    return DeleteResponse(deleted=True, id=conversation_id)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_messages(conversation_id: str, db: Session = Depends(get_db)) -> list[Message]:
    require_conversation(db, conversation_id)
    return list(
        db.scalars(
            select(Message)
            .options(selectinload(Message.citations))
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    )


@router.get("/{conversation_id}/messages/{message_id}/verify", response_model=VerificationResponse)
async def verify_answer(
    conversation_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    base: Settings = Depends(get_settings),
) -> VerificationResponse:
    """Score each sentence of a persisted assistant answer against the documents.

    Read-only and idempotent: the answer is never modified, and results are
    cached in-process per message (messages are immutable once persisted).
    """

    def run() -> VerificationResult:
        message = db.scalar(
            select(Message)
            .options(selectinload(Message.citations))
            .where(Message.id == message_id, Message.conversation_id == conversation_id)
        )
        if message is None or message.role != MessageRole.ASSISTANT:
            raise GroundedPdfError(
                "Assistant message not found", code="message_not_found", status_code=404
            )
        runtime = effective_settings(db, base)
        return verify_message(db, runtime, get_embedding_provider(), get_vector_store(), message)

    result = await run_in_threadpool(run)
    return VerificationResponse(
        message_id=result.message_id,
        generated_at=result.generated_at,
        sentences=[
            VerificationSentenceResponse(
                text=sentence.text,
                verdict=sentence.verdict,
                score=sentence.score,
                source=(
                    VerificationSourceResponse(
                        document_id=sentence.source.document_id,
                        document_name=sentence.source.document_name,
                        page_number=sentence.source.page_number,
                        excerpt=sentence.source.excerpt,
                    )
                    if sentence.source
                    else None
                ),
            )
            for sentence in result.sentences
        ],
    )


@router.get("/{conversation_id}/export")
async def export_conversation(
    conversation_id: str,
    export_format: ExportFormat = Query("markdown", alias="format"),
    db: Session = Depends(get_db),
    base: Settings = Depends(get_settings),
) -> Response:
    """Download the conversation as Markdown or self-contained HTML.

    The export is rendered entirely from persisted records (messages in creation
    order, citation rows, runtime settings, and recomputed verification
    summaries); browser state is never the source.
    """

    def run() -> ConversationExport:
        conversation = db.scalar(
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.citations))
            .where(Conversation.id == conversation_id)
        )
        if conversation is None:
            raise GroundedPdfError(
                "Conversation not found", code="conversation_not_found", status_code=404
            )
        runtime = effective_settings(db, base)
        return build_export(
            db, runtime, get_embedding_provider(), get_vector_store(), conversation, export_format
        )

    export = await run_in_threadpool(run)
    return Response(
        content=export.content,
        media_type=export.media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


@router.post("/{conversation_id}/messages", response_model=AnswerResponse)
async def submit_question(
    conversation_id: str,
    payload: QuestionRequest,
    db: Session = Depends(get_db),
    base: Settings = Depends(get_settings),
) -> AnswerResponse:
    service = make_chat_service(db, base)
    if payload.mode == "compare":
        user_message, sections = await run_in_threadpool(
            service.prepare_compare, db, conversation_id, payload.question
        )
        async for _token in service.compare_events(sections):
            pass  # Sections accumulate their finalized text while streaming.
        assistant = await run_in_threadpool(
            service.persist_compare_answer, db, conversation_id, sections
        )
    else:
        user_message, citations, prompt = await run_in_threadpool(
            service.prepare, db, conversation_id, payload.question
        )
        parts = [token async for token in service.tokens(prompt)]
        assistant = await run_in_threadpool(
            service.persist_answer, db, conversation_id, "".join(parts), citations
        )
    return AnswerResponse(
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant),
    )


@router.post("/{conversation_id}/messages/stream")
async def stream_question(
    conversation_id: str,
    payload: QuestionRequest,
    db: Session = Depends(get_db),
    base: Settings = Depends(get_settings),
) -> StreamingResponse:
    service = make_chat_service(db, base)
    sections: list[CompareSection] = []
    if payload.mode == "compare":
        user_message, sections = await run_in_threadpool(
            service.prepare_compare, db, conversation_id, payload.question
        )
        citations = [citation for section in sections for citation in section.citations]
        prompt = None
    else:
        user_message, citations, prompt = await run_in_threadpool(
            service.prepare, db, conversation_id, payload.question
        )

    async def events() -> AsyncIterator[str]:
        metadata = {
            "user_message": MessageResponse.model_validate(user_message).model_dump(mode="json"),
            "citations": [
                {
                    "id": f"pending-{citation.ordinal}",
                    "document_id": citation.document_id,
                    "document_name": citation.document_name,
                    "page_number": citation.page_number,
                    "excerpt": citation.excerpt,
                    "retrieval_score": citation.score,
                    "ordinal": citation.ordinal,
                }
                for citation in citations
            ],
        }
        yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"
        try:
            if payload.mode == "compare":
                async for safe_token in service.compare_events(sections):
                    yield f"event: token\ndata: {json.dumps({'token': safe_token})}\n\n"
                assistant = await run_in_threadpool(
                    service.persist_compare_answer, db, conversation_id, sections
                )
            else:
                answer = ""
                citation_filter = StreamingCitationFilter(citations)
                async for token in service.tokens(prompt):
                    safe_token = citation_filter.feed(token)
                    if safe_token:
                        answer += safe_token
                        yield f"event: token\ndata: {json.dumps({'token': safe_token})}\n\n"
                trailing_text = citation_filter.finish()
                if trailing_text:
                    answer += trailing_text
                    yield f"event: token\ndata: {json.dumps({'token': trailing_text})}\n\n"
                cited_answer = service.finalize_answer(answer, citations)
                if cited_answer != answer and cited_answer.startswith(answer):
                    suffix = cited_answer[len(answer) :]
                    yield f"event: token\ndata: {json.dumps({'token': suffix})}\n\n"
                answer = cited_answer
                assistant = await run_in_threadpool(
                    service.persist_answer, db, conversation_id, answer, citations
                )
            done = MessageResponse.model_validate(assistant).model_dump(mode="json")
            yield f"event: done\ndata: {json.dumps(done)}\n\n"
        except asyncio.CancelledError:
            db.rollback()
            raise
        except GroundedPdfError as exc:
            db.rollback()
            error = {"code": exc.code, "message": exc.message, "status": exc.status_code}
            yield f"event: error\ndata: {json.dumps(error)}\n\n"
        except Exception:
            db.rollback()
            logger.exception("streaming_answer_failed", extra={"conversation_id": conversation_id})
            error = {
                "code": "internal_error",
                "message": "The answer stream failed unexpectedly. Retry the question.",
                "status": 500,
            }
            yield f"event: error\ndata: {json.dumps(error)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
