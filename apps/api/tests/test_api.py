from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import GroundedPdfError
from app.core.middleware import RateLimitMiddleware, RequestSizeLimitMiddleware
from app.main import app as main_app
from app.models.entities import ApplicationSetting, Document, ProcessingStatus


def test_health_and_validation_responses(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["database"]["status"] == "ok"

    invalid = client.post("/api/v1/conversations", json={"title": ""})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"

    whitespace = client.post("/api/v1/conversations", json={"title": "   "})
    assert whitespace.status_code == 422


def test_request_ids_are_validated_before_response_reflection(client: TestClient) -> None:
    valid = client.get("/api/v1/health", headers={"X-Request-ID": "audit-run:123"})
    invalid = client.get("/api/v1/health", headers={"X-Request-ID": "not a safe id"})

    assert valid.headers["X-Request-ID"] == "audit-run:123"
    assert invalid.headers["X-Request-ID"] != "not a safe id"
    assert len(invalid.headers["X-Request-ID"]) == 36


def test_loopback_cors_and_error_schema_are_documented(client: TestClient) -> None:
    response = client.options(
        "/api/v1/documents",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    schema = client.get("/openapi.json").json()
    assert "ErrorResponse" in schema["components"]["schemas"]


def test_upload_rejects_unsupported_file(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents", files=[("files", ("notes.txt", b"plain text", "text/plain"))]
    )
    assert response.status_code == 202
    assert response.json()["documents"] == []
    assert response.json()["rejected"][0]["code"] == "unsupported_extension"


def test_upload_rejects_conflicting_content_type(client: TestClient, sample_pdf: Path) -> None:
    response = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "text/plain"))],
    )
    assert response.status_code == 202
    assert response.json()["documents"] == []
    assert response.json()["rejected"][0]["code"] == "unsupported_content_type"


def test_upload_limit_removes_partial_file(client: TestClient, settings: Settings) -> None:
    settings.max_upload_mb = 1
    response = client.post(
        "/api/v1/documents",
        files=[("files", ("large.pdf", b"%PDF-" + b"x" * (1024 * 1024), "application/pdf"))],
    )
    assert response.status_code == 202
    assert response.json()["rejected"][0]["code"] == "file_too_large"
    assert list(settings.upload_dir.iterdir()) == []


def test_upload_and_duplicate_protection(client: TestClient, db: Session, sample_pdf: Path) -> None:
    first = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    )
    second = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["documents"][0]["id"] == second.json()["documents"][0]["id"]
    assert first.json()["documents"][0]["created_at"].endswith(("Z", "+00:00"))
    assert len(list(db.scalars(select(Document)))) == 1


def test_duplicate_files_in_one_request_are_returned_once(
    client: TestClient, db: Session, sample_pdf: Path
) -> None:
    pdf = sample_pdf.read_bytes()
    response = client.post(
        "/api/v1/documents",
        files=[
            ("files", ("first.pdf", pdf, "application/pdf")),
            ("files", ("second.pdf", pdf, "application/pdf")),
        ],
    )

    assert response.status_code == 202
    assert len(response.json()["documents"]) == 1
    assert len(list(db.scalars(select(Document)))) == 1


def test_upload_enforces_configured_file_count(
    client: TestClient, settings: Settings, sample_pdf: Path
) -> None:
    settings.max_upload_files = 1
    pdf = sample_pdf.read_bytes()
    response = client.post(
        "/api/v1/documents",
        files=[
            ("files", ("first.pdf", pdf, "application/pdf")),
            ("files", ("second.pdf", pdf, "application/pdf")),
        ],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "too_many_files"


def test_upload_enforces_aggregate_raw_file_size(client: TestClient, settings: Settings) -> None:
    settings.max_upload_batch_mb = 1
    content = b"%PDF-" + b"x" * (600 * 1024)
    response = client.post(
        "/api/v1/documents",
        files=[
            ("files", ("first.pdf", content, "application/pdf")),
            ("files", ("second.pdf", content, "application/pdf")),
        ],
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_batch_too_large"
    assert list(settings.upload_dir.iterdir()) == []


def test_upload_request_limit_covers_streams_without_content_length() -> None:
    limited_app = FastAPI()

    @limited_app.exception_handler(GroundedPdfError)
    async def handle_grounded_error(_request: Request, exc: GroundedPdfError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @limited_app.post("/upload")
    async def consume_upload(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    limited_app.add_middleware(RequestSizeLimitMiddleware, max_bytes=8, upload_path="/upload")
    with TestClient(limited_app) as limited_client:
        response = limited_client.post("/upload", content=iter([b"12345", b"6789"]))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_batch_too_large"


def test_real_app_returns_413_for_oversized_chunked_upload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full app.main middleware stack must answer 413, not 500, for chunked bodies."""
    stack: object = main_app.middleware_stack
    while stack is not None and not isinstance(stack, RequestSizeLimitMiddleware):
        stack = getattr(stack, "app", None)
    assert isinstance(stack, RequestSizeLimitMiddleware)
    monkeypatch.setattr(stack, "max_bytes", 8)

    response = client.post(
        "/api/v1/documents",
        content=iter([b"12345", b"6789"]),
        headers={"Content-Type": "multipart/form-data; boundary=upload"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_batch_too_large"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"]


def test_oversized_non_upload_request_body_is_rejected(client: TestClient) -> None:
    declared = client.post(
        "/api/v1/conversations",
        content=b"",
        headers={"Content-Length": str(2 * 1024 * 1024)},
    )
    assert declared.status_code == 413
    assert declared.json()["error"]["code"] == "request_too_large"


def test_rate_limiter_returns_429_after_limit() -> None:
    limited_app = FastAPI()

    @limited_app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    limited_app.add_middleware(RateLimitMiddleware, requests_per_minute=2)
    with TestClient(limited_app) as limited_client:
        assert limited_client.get("/ping").status_code == 200
        assert limited_client.get("/ping").status_code == 200
        limited = limited_client.get("/ping")

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert limited.headers["Retry-After"] == "60"


def test_declared_oversized_upload_is_rejected_before_body_parsing(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        content=b"",
        headers={"Content-Length": str(202 * 1024 * 1024)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_batch_too_large"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"]


def test_upload_batch_limit_cannot_be_smaller_than_file_limit() -> None:
    with pytest.raises(ValidationError, match="max_upload_batch_mb"):
        Settings(max_upload_mb=51, max_upload_batch_mb=50)


def test_duplicate_upload_restores_a_missing_stored_file(
    client: TestClient, db: Session, settings: Settings, sample_pdf: Path
) -> None:
    first = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    ).json()["documents"][0]
    document = db.get(Document, first["id"])
    assert document is not None
    stored_path = settings.upload_dir / document.storage_name
    stored_path.unlink()
    document.status = ProcessingStatus.FAILED
    db.commit()

    restored = client.post(
        "/api/v1/documents",
        files=[("files", ("restored.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    )

    db.refresh(document)
    assert restored.status_code == 202
    assert restored.json()["documents"][0]["id"] == document.id
    assert document.status == ProcessingStatus.QUEUED
    assert document.original_name == "restored.pdf"
    assert stored_path.read_bytes() == sample_pdf.read_bytes()


def test_document_cannot_be_deleted_while_processing(client: TestClient, sample_pdf: Path) -> None:
    uploaded = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    ).json()["documents"][0]
    response = client.delete(f"/api/v1/documents/{uploaded['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_processing"


def test_document_retry_can_only_be_claimed_once(
    client: TestClient, db: Session, sample_pdf: Path
) -> None:
    uploaded = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    ).json()["documents"][0]
    document = db.get(Document, uploaded["id"])
    assert document is not None
    document.status = ProcessingStatus.FAILED
    db.commit()

    first = client.post(f"/api/v1/documents/{document.id}/retry")
    second = client.post(f"/api/v1/documents/{document.id}/retry")

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_processing"


def test_document_file_is_served_inline(
    client: TestClient, db: Session, settings: Settings, sample_pdf: Path
) -> None:
    uploaded = client.post(
        "/api/v1/documents",
        files=[("files", ("sample.pdf", sample_pdf.read_bytes(), "application/pdf"))],
    ).json()["documents"][0]

    served = client.get(f"/api/v1/documents/{uploaded['id']}/file")

    assert served.status_code == 200
    assert served.headers["content-type"] == "application/pdf"
    assert served.content == sample_pdf.read_bytes()

    document = db.get(Document, uploaded["id"])
    assert document is not None
    (settings.upload_dir / document.storage_name).unlink()

    missing = client.get(f"/api/v1/documents/{uploaded['id']}/file")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "document_file_missing"


def test_conversation_crud_and_document_selection(client: TestClient) -> None:
    created = client.post("/api/v1/conversations", json={"title": "Research", "document_ids": []})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    renamed = client.patch(
        f"/api/v1/conversations/{conversation_id}", json={"title": "Pilot study"}
    )
    assert renamed.json()["title"] == "Pilot study"
    detail = client.get(f"/api/v1/conversations/{conversation_id}")
    assert detail.json()["messages"] == []
    deleted = client.delete(f"/api/v1/conversations/{conversation_id}")
    assert deleted.json() == {"deleted": True, "id": conversation_id}


def test_question_requires_a_ready_document(client: TestClient) -> None:
    conversation = client.post(
        "/api/v1/conversations", json={"title": "Empty", "document_ids": []}
    ).json()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages", json={"question": "What happened?"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_ready_documents"

    whitespace = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages", json={"question": "   "}
    )
    assert whitespace.status_code == 422
    assert whitespace.json()["error"]["code"] == "validation_error"


def test_safe_settings_do_not_expose_secrets(client: TestClient) -> None:
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    payload = response.json()
    assert "openai_api_key" not in payload
    assert "provider_configured" not in payload
    assert payload["embedding_model"]

    invalid = client.patch("/api/v1/settings", json={"model_name": "   "})
    assert invalid.status_code == 422


def test_invalid_persisted_runtime_setting_does_not_break_settings_endpoint(
    client: TestClient, db: Session, settings: Settings
) -> None:
    db.add(ApplicationSetting(key="chunk_size", value='"not-an-integer"'))
    db.commit()

    response = client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["chunk_size"] == settings.chunk_size
