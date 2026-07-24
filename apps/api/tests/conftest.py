from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

os.environ["GROUNDEDPDF_ENVIRONMENT"] = "test"
os.environ["GROUNDEDPDF_MODEL_PROVIDER"] = "mock"
os.environ["GROUNDEDPDF_DATABASE_URL"] = "sqlite:///./data/test-bootstrap.db"

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.dependencies import clear_service_caches


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        model_provider="mock",
        chunk_size=240,
        chunk_overlap=40,
        retrieval_min_score=0.05,
    )


@pytest.fixture
def db(settings: Settings) -> Generator[Session, None, None]:
    settings.ensure_data_directories()
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: object, _record: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, expire_on_commit=False)
    with local_session() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(
    db: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr("app.api.routes.documents.process_document", lambda _document_id: None)
    clear_service_caches()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    clear_service_caches()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sample.pdf"
    document = fitz.open()
    page_one = document.new_page()
    page_one.insert_text(
        (72, 72),
        "GroundedPDF Sample Report\nThe project began in 2024 and protects local document privacy.",
        fontsize=12,
    )
    page_two = document.new_page()
    page_two.insert_text(
        (72, 72),
        "Research Findings\nThe measured efficiency gain was 37 percent during the pilot study.",
        fontsize=12,
    )
    document.set_metadata({"title": "GroundedPDF Sample Report", "author": "GroundedPDF"})
    document.save(path)
    document.close()
    return path
