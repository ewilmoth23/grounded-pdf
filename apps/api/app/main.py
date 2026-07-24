from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import GroundedPdfError
from app.core.logging import configure_logging
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
)
from app.db.session import SessionLocal
from app.providers.factory import aclose_chat_providers
from app.schemas.common import ErrorResponse
from app.workers.ingestion import recover_interrupted_ingestion

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


def create_app(app_settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        app_settings.ensure_data_directories()
        with SessionLocal() as db:
            recover_interrupted_ingestion(db)
        logger.info("application_started")
        yield
        await aclose_chat_providers()
        logger.info("application_stopped")

    # Interactive docs and the OpenAPI schema are development conveniences;
    # production serves the application only.
    docs_enabled = app_settings.environment != "production"
    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        description="Local-first PDF question answering with verifiable page-level citations.",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        responses={
            status_code: {"model": ErrorResponse, "description": "GroundedPDF error response"}
            for status_code in (400, 404, 409, 413, 422, 429, 500, 503)
        },
    )
    application.add_middleware(
        RateLimitMiddleware, requests_per_minute=app_settings.rate_limit_per_minute
    )
    application.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=app_settings.max_upload_request_bytes,
        upload_path=f"{app_settings.api_prefix}/documents",
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Total-Count"],
    )
    application.include_router(api_router, prefix=app_settings.api_prefix)

    @application.exception_handler(GroundedPdfError)
    async def groundedpdf_error(request: Request, exc: GroundedPdfError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {"msg": "Invalid request"}
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": first.get("msg", "Invalid request"),
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception("unhandled_request_error", extra={"request_id": request_id})
        headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred",
                    "request_id": request_id,
                }
            },
            headers=headers,
        )

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        info = {"name": app_settings.app_name, "health": f"{app_settings.api_prefix}/health"}
        if docs_enabled:
            info["docs"] = "/docs"
        return info

    return application


app = create_app(settings)
