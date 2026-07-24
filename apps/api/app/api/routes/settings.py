from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import GroundedPdfError
from app.db.session import get_db
from app.rag.verification import clear_verification_cache
from app.schemas.settings import RuntimeSettingsUpdate, SafeSettingsResponse
from app.services.settings import effective_settings, update_runtime_settings

router = APIRouter()


def safe_response(settings: Settings) -> SafeSettingsResponse:
    return SafeSettingsResponse(
        environment=settings.environment,
        model_provider=settings.model_provider,
        model_name=settings.model_name,
        embedding_model=settings.embedding_model,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        retrieval_count=settings.retrieval_count,
        max_upload_mb=settings.max_upload_mb,
        max_upload_batch_mb=settings.max_upload_batch_mb,
        max_upload_files=settings.max_upload_files,
        temperature=settings.temperature,
        max_output_tokens=settings.max_output_tokens,
        ocr_enabled=settings.enable_ocr,
    )


@router.get("", response_model=SafeSettingsResponse)
def get_safe_settings(
    db: Session = Depends(get_db), base: Settings = Depends(get_settings)
) -> SafeSettingsResponse:
    return safe_response(effective_settings(db, base))


@router.patch("", response_model=SafeSettingsResponse)
def patch_settings(
    payload: RuntimeSettingsUpdate,
    db: Session = Depends(get_db),
    base: Settings = Depends(get_settings),
) -> SafeSettingsResponse:
    try:
        updated = update_runtime_settings(db, payload, base)
    except ValueError as exc:
        raise GroundedPdfError(str(exc), code="invalid_settings", status_code=422) from exc
    # Runtime settings feed retrieval and verification; cached verdicts may no
    # longer reflect the effective configuration.
    clear_verification_cache()
    return safe_response(updated)
