from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repository_env_file() -> Path:
    """Use the repository-level .env even when commands run from apps/api."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env.example").is_file():
            return parent / ".env"
    return Path(".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_repository_env_file(),
        env_prefix="GROUNDEDPDF_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "GroundedPDF"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/groundedpdf.db"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    max_upload_mb: int = Field(default=50, ge=1, le=2048)
    max_upload_batch_mb: int = Field(default=200, ge=1, le=4096)
    max_upload_files: int = Field(default=20, ge=1, le=100)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = Field(default=900, ge=200, le=4000)
    chunk_overlap: int = Field(default=150, ge=0, le=1000)
    retrieval_count: int = Field(default=6, ge=1, le=20)
    retrieval_min_score: float = Field(default=0.15, ge=-1.0, le=1.0)
    retrieval_semantic_confidence_score: float = Field(default=0.45, ge=-1.0, le=1.0)
    verification_supported_score: float = Field(default=0.6, ge=0.0, le=1.0)
    verification_weak_score: float = Field(default=0.35, ge=0.0, le=1.0)

    model_provider: Literal["ollama", "openai_compatible", "mock"] = "ollama"
    model_name: str = "llama3.2:3b"
    ollama_base_url: str = "http://localhost:11434"
    openai_base_url: str = "http://localhost:8001/v1"
    openai_api_key: str | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_output_tokens: int = Field(default=800, ge=32, le=32_000)
    model_timeout_seconds: float = Field(default=120, ge=1, le=600)
    enable_ocr: bool = False

    @model_validator(mode="after")
    def overlap_is_smaller_than_chunk(self) -> Settings:
        if self.chunk_overlap > self.chunk_size // 2:
            raise ValueError("chunk_overlap must be at most half of chunk_size")
        if self.max_upload_batch_mb < self.max_upload_mb:
            raise ValueError("max_upload_batch_mb must be at least max_upload_mb")
        if self.verification_weak_score > self.verification_supported_score:
            raise ValueError("verification_weak_score must be at most verification_supported_score")
        self.model_name = self.model_name.strip()
        if not self.model_name:
            raise ValueError("model_name must not be blank")
        if self.model_provider == "mock" and self.environment != "test":
            raise ValueError("The mock model provider is available only in the test environment")
        return self

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_upload_batch_bytes(self) -> int:
        return self.max_upload_batch_mb * 1024 * 1024

    @property
    def max_upload_request_bytes(self) -> int:
        # Reserve one MiB for multipart boundaries and per-file headers. Individual
        # files are still limited by max_upload_bytes while they stream to disk.
        return self.max_upload_batch_bytes + 1024 * 1024

    def ensure_data_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
