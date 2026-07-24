from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import GroundedPdfError
from app.core.logging import configure_logging
from app.core.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
)
from app.db.session import SessionLocal
from app.schemas.common import ErrorResponse
from app.workers.ingestion import recover_interrupted_ingestion

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.ensure_data_directories()
    with SessionLocal() as db:
        recover_interrupted_ingestion(db)
    logger.info("application_started")
    yield
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Local-first PDF question answering with verifiable page-level citations.",
    lifespan=lifespan,
    responses={
        status_code: {"model": ErrorResponse, "description": "GroundedPDF error response"}
        for status_code in (400, 404, 409, 413, 422, 429, 500, 503)
    },
)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_bytes=settings.max_upload_request_bytes,
    upload_path=f"{settings.api_prefix}/documents",
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.exception_handler(GroundedPdfError)
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


@app.exception_handler(RequestValidationError)
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


@app.exception_handler(Exception)
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


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_prefix}/health"}
