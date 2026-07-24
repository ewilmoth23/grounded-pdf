from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.entities import ApplicationSetting
from app.schemas.settings import RuntimeSettingsUpdate

logger = logging.getLogger(__name__)

RUNTIME_KEYS = {
    "model_provider",
    "model_name",
    "chunk_size",
    "chunk_overlap",
    "retrieval_count",
    "temperature",
    "max_output_tokens",
}
RUNTIME_KEY_ORDER = (
    "model_provider",
    "model_name",
    "chunk_size",
    "chunk_overlap",
    "retrieval_count",
    "temperature",
    "max_output_tokens",
)


def effective_settings(db: Session, base: Settings) -> Settings:
    rows = db.scalars(select(ApplicationSetting).where(ApplicationSetting.key.in_(RUNTIME_KEYS)))
    overrides: dict[str, Any] = {}
    for row in rows:
        try:
            overrides[row.key] = json.loads(row.value)
        except json.JSONDecodeError:
            logger.warning("invalid_runtime_setting_ignored", extra={"setting_key": row.key})
            continue
    try:
        return Settings.model_validate({**base.model_dump(), **overrides})
    except ValueError:
        logger.warning("invalid_runtime_settings_recovering")

    recovered = base
    for key in RUNTIME_KEY_ORDER:
        if key not in overrides:
            continue
        try:
            recovered = Settings.model_validate({**recovered.model_dump(), key: overrides[key]})
        except ValueError:
            logger.warning("invalid_runtime_setting_ignored", extra={"setting_key": key})
    return recovered


def update_runtime_settings(db: Session, update: RuntimeSettingsUpdate, base: Settings) -> Settings:
    values = update.model_dump(exclude_none=True)
    current = effective_settings(db, base)
    merged = Settings.model_validate({**current.model_dump(), **values})
    for key, value in values.items():
        row = db.get(ApplicationSetting, key)
        if row:
            row.value = json.dumps(value)
        else:
            db.add(ApplicationSetting(key=key, value=json.dumps(value)))
    db.commit()
    return merged
