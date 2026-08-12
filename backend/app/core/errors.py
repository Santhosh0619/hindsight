from fastapi import Request, status
from fastapi.responses import JSONResponse


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


class LLMUnavailableError(AppError):
    """Raised when every configured LLM provider is unreachable or out of quota.

    Callers must degrade (serve deterministic output / cached results), never crash a
    request because of this.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "llm_unavailable"


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "detail": exc.detail,
            }
        },
    )
