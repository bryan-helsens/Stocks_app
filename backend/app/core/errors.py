"""Uniform error handling.

Every error returned to a client uses a single envelope shape::

    {"error": {"code": "not_found", "message": "...", "details": {...}}}

Stack traces and internal exception text are never leaked to clients. Domain
and application layers raise the typed exceptions below; the FastAPI handlers
(registered in :func:`register_exception_handlers`) translate them to HTTP.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base class for all application/domain errors.

    Attributes:
        code: stable machine-readable identifier (snake_case).
        message: human-readable, safe-to-display message.
        status_code: HTTP status to map to.
        details: optional structured context (must be JSON-serialisable).
    """

    code: str = "app_error"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    code = "validation_error"
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


class ConflictError(AppError):
    """E.g. duplicate transaction, already-existing resource."""

    code = "conflict"
    status_code = status.HTTP_409_CONFLICT


class AuthenticationError(AppError):
    code = "authentication_error"
    status_code = status.HTTP_401_UNAUTHORIZED


class PermissionError_(AppError):  # noqa: N801 - avoid shadowing builtin name
    code = "forbidden"
    status_code = status.HTTP_403_FORBIDDEN


class RateLimitError(AppError):
    code = "rate_limited"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class ExternalServiceError(AppError):
    """A provider (market data, AI, notifier) failed."""

    code = "external_service_error"
    status_code = status.HTTP_502_BAD_GATEWAY


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to *app*."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("app_error", code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                "validation_error",
                "Request validation failed.",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internals; log full detail server-side only.
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "An unexpected error occurred."),
        )
