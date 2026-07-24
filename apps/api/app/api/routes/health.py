from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.providers.factory import create_chat_provider
from app.schemas.health import ComponentHealth, HealthResponse
from app.services.dependencies import get_vector_store
from app.services.settings import effective_settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health(
    db: Session = Depends(get_db), base_settings: Settings = Depends(get_settings)
) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        database = ComponentHealth(status="ok")
    except Exception:
        db.rollback()
        logger.exception("database_health_check_failed")
        database = ComponentHealth(status="unavailable", detail="Database check failed")

    vector_ok, vector_detail = get_vector_store().health()
    vector_store = ComponentHealth(
        status="ok" if vector_ok else "unavailable", detail=vector_detail
    )
    runtime = effective_settings(db, base_settings) if database.status == "ok" else base_settings
    provider_ok, provider_detail = await create_chat_provider(runtime).health()
    model_provider = ComponentHealth(
        status="ok" if provider_ok else "unavailable", detail=provider_detail
    )
    overall = (
        "ok"
        if database.status == "ok" and vector_store.status == "ok" and model_provider.status == "ok"
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        version=base_settings.version,
        database=database,
        vector_store=vector_store,
        model_provider=model_provider,
    )
