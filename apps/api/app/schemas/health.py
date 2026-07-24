from typing import Literal

from pydantic import BaseModel


class ComponentHealth(BaseModel):
    status: Literal["ok", "unavailable"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: ComponentHealth
    vector_store: ComponentHealth
    model_provider: ComponentHealth
