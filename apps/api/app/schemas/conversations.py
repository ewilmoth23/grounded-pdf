from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.entities import MessageRole


class StrippedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ConversationCreate(StrippedInput):
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    document_ids: list[str] = Field(default_factory=list, max_length=50)


class ConversationRename(StrippedInput):
    title: str = Field(min_length=1, max_length=200)


class ConversationDocumentsUpdate(StrippedInput):
    document_ids: list[str] = Field(max_length=50)


class CitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # None once the cited document has been deleted; the snapshot fields below
    # keep the citation renderable.
    document_id: str | None
    document_name: str
    page_number: int
    excerpt: str
    retrieval_score: float | None
    ordinal: int


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: MessageRole
    content: str
    mode: str | None = None
    citations: list[CitationResponse] = Field(default_factory=list)
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    document_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)


class QuestionRequest(StrippedInput):
    question: str = Field(min_length=2, max_length=4000)
    mode: Literal["answer", "compare"] = "answer"


class AnswerResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


class VerificationSourceResponse(BaseModel):
    document_id: str
    document_name: str
    page_number: int
    excerpt: str


class VerificationSentenceResponse(BaseModel):
    text: str
    verdict: Literal["supported", "weak", "unsupported"]
    score: float
    source: VerificationSourceResponse | None


class VerificationResponse(BaseModel):
    message_id: str
    generated_at: datetime
    sentences: list[VerificationSentenceResponse]
