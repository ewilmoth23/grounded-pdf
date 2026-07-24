from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.entities import ProcessingStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    title: str | None
    file_size: int
    page_count: int
    searchable_page_count: int
    status: ProcessingStatus
    processing_error: str | None
    stale_index: bool = False
    created_at: datetime
    updated_at: datetime


class OutlineEntry(BaseModel):
    level: int
    title: str
    page: int


class DocumentDetailResponse(DocumentResponse):
    scanned_page_numbers: list[int] = Field(default_factory=list)
    chunk_count: int = 0
    outline: list[OutlineEntry] | None = None


class ReprocessStaleResponse(BaseModel):
    queued: int
    # Stale documents left unclaimed by this call (the endpoint queues a
    # bounded batch per request); another call will pick them up.
    remaining: int


class UploadResponse(BaseModel):
    documents: list[DocumentResponse]
    rejected: list["RejectedUpload"] = Field(default_factory=list)


class RejectedUpload(BaseModel):
    filename: str
    code: str
    message: str


class ProcessingStatusResponse(BaseModel):
    id: str
    status: ProcessingStatus
    processing_error: str | None
    page_count: int
    searchable_page_count: int
