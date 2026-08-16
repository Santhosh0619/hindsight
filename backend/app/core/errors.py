import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for typed application exceptions.

    Every subclass carries an HTTP status, a stable machine-readable code, and a
    human-readable message, so `app_error_handler` can render a consistent envelope
    without inspecting exception internals.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class LLMUnavailableError(AppError):
    """Raised when every configured LLM provider is unreachable or out of quota.

    Callers must degrade (serve deterministic output / cached results), never crash a
    request because of this.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "llm_unavailable"


class RequestTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "request_too_large"


def get_request_id() -> str | None:
    # RequestIDMiddleware (app/core/logging.py) binds this to structlog's contextvars
    # at the start of every request -- reading it back here (rather than threading a
    # request_id parameter through every raise site) is what lets both error handlers
    # below share one envelope shape without either one drifting from the other.
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    return request_id if isinstance(request_id, str) else None


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
                "request_id": get_request_id(),
            }
        },
    )


async def app_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Anything not raised as a typed AppError is, by definition, a bug -- log it with
    # the full traceback and the request's correlation id server-side, but the client
    # only ever sees a generic message. Never echo exc's own message/type: that's
    # exactly the internals this handler exists to keep off the wire.
    logger.exception("unhandled_exception", request_id=get_request_id())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "detail": None,
                "request_id": get_request_id(),
            }
        },
    )
