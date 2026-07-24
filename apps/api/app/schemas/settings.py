from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SafeSettingsResponse(BaseModel):
    environment: str
    model_provider: str
    model_name: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    retrieval_count: int
    max_upload_mb: int
    max_upload_batch_mb: int
    max_upload_files: int
    temperature: float
    max_output_tokens: int
    ocr_enabled: bool


class RuntimeSettingsUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    model_provider: Literal["ollama", "openai_compatible", "mock"] | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    chunk_size: int | None = Field(default=None, ge=200, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)
    retrieval_count: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=32, le=32_000)

    @model_validator(mode="after")
    def overlap_less_than_size(self) -> "RuntimeSettingsUpdate":
        if (
            self.chunk_size is not None
            and self.chunk_overlap is not None
            and self.chunk_overlap > self.chunk_size // 2
        ):
            raise ValueError("chunk_overlap must be at most half of chunk_size")
        return self
