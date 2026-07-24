from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,128}")
DEFAULT_BODY_LIMIT_BYTES = 1024 * 1024
RATE_LIMIT_SWEEP_INTERVAL = 1024
RATE_LIMIT_MAX_KEYS = 1024


class BodyLimitExceeded(BaseException):
    """Internal signal raised from a wrapped ``receive`` when a body limit is hit.

    Derives from ``BaseException`` so framework-level ``except Exception`` blocks
    (for example FastAPI's request-body parsing) cannot convert it into a
    different response before ``RequestSizeLimitMiddleware`` sends its 413.
    It never escapes ``RequestSizeLimitMiddleware.__call__``.
    """

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RequestSizeLimitMiddleware:
    """Limit request bodies even when no Content-Length is supplied.

    Upload requests are capped by the configured batch limit; every other
    request body is capped at ``DEFAULT_BODY_LIMIT_BYTES``.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        upload_path: str,
        default_max_bytes: int = DEFAULT_BODY_LIMIT_BYTES,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.upload_path = upload_path.rstrip("/")
        self.default_max_bytes = default_max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", "")).rstrip("/")
        if scope["method"] == "POST" and path == self.upload_path:
            limit = self.max_bytes
            code = "upload_batch_too_large"
            message = self._message()
        else:
            limit = self.default_max_bytes
            code = "request_too_large"
            message = self._general_message()

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                await self._reject(scope, receive, send, "Invalid Content-Length header", code)
                return
            if declared_size < 0:
                await self._reject(scope, receive, send, "Invalid Content-Length header", code)
                return
            if declared_size > limit:
                await self._reject(scope, receive, send, message, code)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            incoming = await receive()
            if incoming["type"] == "http.request":
                received += len(incoming.get("body", b""))
                if received > limit:
                    raise BodyLimitExceeded(message, code)
            return incoming

        async def tracking_send(outgoing: Message) -> None:
            nonlocal response_started
            if outgoing["type"] == "http.response.start":
                response_started = True
            await send(outgoing)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyLimitExceeded as exc:
            if not response_started:
                await self._reject(scope, receive, send, exc.message, exc.code)
        except BaseExceptionGroup as group:
            # anyio task groups (e.g. inside BaseHTTPMiddleware) may wrap the
            # signal together with byproduct errors such as "No response
            # returned."; the 413 response takes precedence over those.
            matched, _rest = group.split(BodyLimitExceeded)
            if matched is None:
                raise
            if not response_started:
                limit_exc = self._first_limit_exception(matched)
                await self._reject(scope, receive, send, limit_exc.message, limit_exc.code)

    def _message(self) -> str:
        limit_mb = (self.max_bytes // (1024 * 1024)) - 1
        return f"Upload request exceeds the {limit_mb} MB batch limit"

    def _general_message(self) -> str:
        limit_mb = self.default_max_bytes // (1024 * 1024)
        return f"Request body exceeds the {limit_mb} MB limit"

    @staticmethod
    def _first_limit_exception(group: BaseExceptionGroup[BodyLimitExceeded]) -> BodyLimitExceeded:
        current: BaseException = group
        while isinstance(current, BaseExceptionGroup):
            current = current.exceptions[0]
        assert isinstance(current, BodyLimitExceeded)
        return current

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, message: str, code: str) -> None:
        response = JSONResponse(
            status_code=413,
            content={"error": {"code": code, "message": message}},
        )
        await response(scope, receive, send)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if REQUEST_ID_RE.fullmatch(supplied_request_id)
            else str(uuid.uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, requests_per_minute: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.limit = requests_per_minute
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self._requests_since_sweep = 0

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.endswith("/health"):
            return await call_next(request)
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        self._requests_since_sweep += 1
        if (
            self._requests_since_sweep >= RATE_LIMIT_SWEEP_INTERVAL
            or len(self.requests) > RATE_LIMIT_MAX_KEYS
        ):
            self._requests_since_sweep = 0
            self._sweep(now)
        bucket = self.requests[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests"}},
                headers={"Retry-After": "60"},
            )
        bucket.append(now)
        return await call_next(request)

    def _sweep(self, now: float) -> None:
        """Drop buckets whose entries have all expired to bound memory usage."""
        for key, bucket in list(self.requests.items()):
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            if not bucket:
                del self.requests[key]
