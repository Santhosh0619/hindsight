from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.core.errors import RequestTooLargeError, get_request_id


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Rejects a request whose declared Content-Length exceeds the configured cap,
    before the body is ever parsed into a Pydantic model.

    See docs/modules/phase-14-hardening/FRD.md "Request size cap" for why this is a
    defense-in-depth check (a request with no Content-Length, e.g. chunked transfer,
    is let through to normal per-field validation rather than blocked here).
    """

    def __init__(self, app: object, *, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        content_length = request.headers.get("content-length")
        oversized = (
            content_length is not None
            and content_length.isdigit()
            and int(content_length) > self._settings.max_request_bytes
        )
        if oversized:
            exc = RequestTooLargeError("Request body too large")
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
        return await call_next(request)
