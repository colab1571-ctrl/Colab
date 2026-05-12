"""
colab_common.errors — Standard error envelope + FastAPI exception handlers.

Standard error response shape:
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found.",
    "details": {},
    "request_id": "..."
  }
}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base error hierarchy
# ---------------------------------------------------------------------------


class AppError(Exception):
    """Base class for all application errors."""

    http_status: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self, request_id: str = "") -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
                "request_id": request_id,
            }
        }


class AuthError(AppError):
    http_status = 401
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message)


class ForbiddenError(AppError):
    http_status = 403
    code = "FORBIDDEN"

    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__(message)


class ValidationError(AppError):
    http_status = 422
    code = "VALIDATION_ERROR"

    def __init__(
        self, message: str = "Validation failed.", *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, details=details)


class NotFoundError(AppError):
    http_status = 404
    code = "NOT_FOUND"

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found.")


class ConflictError(AppError):
    http_status = 409
    code = "CONFLICT"

    def __init__(self, message: str = "Resource conflict.") -> None:
        super().__init__(message)


class RateLimitError(AppError):
    http_status = 429
    code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            "Rate limit exceeded. Please slow down.",
            details={"retry_after_seconds": retry_after},
        )
        self.retry_after = retry_after


class ServiceUnavailableError(AppError):
    http_status = 503
    code = "SERVICE_UNAVAILABLE"

    def __init__(self, message: str = "Service temporarily unavailable.") -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# FastAPI exception handler registration
# ---------------------------------------------------------------------------


def _get_request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def register_handlers(app: FastAPI) -> None:
    """Register all exception handlers on a FastAPI app. Call once at startup."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.warning(
            "AppError",
            extra={
                "code": exc.code,
                "status": exc.http_status,
                "request_id": request_id,
                "error_message": exc.message,
            },
        )
        headers: dict[str, str] = {}
        if isinstance(exc, RateLimitError):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(request_id),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.exception("Unhandled exception", extra={"request_id": request_id})
        error = AppError(str(exc))
        return JSONResponse(
            status_code=500,
            content=error.to_dict(request_id),
        )
