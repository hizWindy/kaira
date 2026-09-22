"""Observability and structured request logging middleware."""

from __future__ import annotations

import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from fastapi.encoders import jsonable_encoder
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from kaira.app.logging import INDENT, detail, http, is_debug, logger

_PROJECT_ROOT = Path.cwd()
_SELF = Path(__file__).resolve()
_TRACE_FRAMES = 8

_SKIP_PATHS = {
    p.strip()
    for p in os.getenv("KAIRA_LOG_SKIP_PATHS", "").split(",")
    if p.strip()
}
_EXPOSE_INTERNALS = os.getenv("APP_ENV", "development") != "production"


def _client_host(request: Request) -> str:
    """Return the client host, or ``unknown`` when the scope has no client."""
    return request.client.host if request.client else "unknown"


def _request_id(request: Request) -> str:
    """Return the assigned correlation id, falling back to a fresh one."""
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())[:8]


def _field_errors(exc: Any) -> list[dict[str, Any]]:
    """Flatten pydantic's error list into field/message/type rows."""
    rows = []
    errors = getattr(exc, "errors", list)()
    for err in errors:
        location = ".".join(str(part) for part in err.get("loc", ())) or "body"
        rows.append(
            {
                "field": location,
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
        )
    return rows


def _app_frames(exc: BaseException) -> list[traceback.FrameSummary]:
    """Return only the traceback frames that live inside this project."""
    frames = []
    for frame in traceback.extract_tb(exc.__traceback__):
        try:
            absolute = Path(frame.filename).resolve()
            relative = absolute.relative_to(_PROJECT_ROOT)
        except (ValueError, OSError):
            continue
        if "site-packages" in relative.parts or absolute == _SELF:
            continue
        frame.filename = relative.as_posix()
        frames.append(frame)
    return frames


def _traceback_block(frames: list[traceback.FrameSummary]) -> str:
    """Render project frames as indented path:line in func + source lines."""
    if not frames:
        return ""
    lines = ["\n" + INDENT + "traceback (innermost last)"]
    for frame in frames[-_TRACE_FRAMES:]:
        lines.append(
            "\n" + INDENT + "  " + f"{frame.filename}:{frame.lineno} in {frame.name}"
        )
        if frame.line:
            lines.append("\n" + INDENT + "      " + frame.line.strip())
    return "".join(lines)


def _log_unhandled(request: Request, exc: BaseException) -> None:
    """Print the one diagnostic block for a crashed request."""
    if getattr(request.state, "error_logged", False):
        return
    request.state.error_logged = True

    frames = _app_frames(exc)
    rows: dict[str, object] = {
        "request": _request_id(request),
        "client": _client_host(request),
        "reason": " ".join((str(exc) or repr(exc)).split()),
    }
    if not frames:
        rows["where"] = "outside project code"

    summary = (
        f"Unhandled {type(exc).__name__} on {request.method} {request.url.path}"
        + detail(**rows)
    )
    if is_debug():
        logger.opt(exception=exc).error(summary)
    else:
        logger.error(summary + _traceback_block(frames))


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    detail_value: object | None = None,
    fields: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the shared error envelope."""
    request_id = _request_id(request)
    error: dict[str, Any] = {
        "code": code,
        "status": status_code,
        "message": message,
        "method": request.method,
        "path": request.url.path,
        "request_id": request_id,
    }
    if fields:
        error["fields"] = fields
    if extra:
        error.update(extra)

    return JSONResponse(
        status_code=status_code,
        content={
            "detail": message if detail_value is None else detail_value,
            "error": error,
        },
        headers={"X-Request-ID": request_id},
    )


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Observability middleware: tags requests with X-Request-ID, measures duration,
    and logs every request using Khaira's status-colored single-line format."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        path = request.url.path
        quiet = path in _SKIP_PATHS

        if is_debug() and not quiet:
            logger.debug(
                f"{request.method} {path} received"
                + detail(request=request_id, client=_client_host(request))
            )

        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            _log_unhandled(request, exc)
            if not quiet:
                http(
                    request.method,
                    path,
                    500,
                    duration_ms,
                    request_id,
                    client=_client_host(request),
                )
            raise

        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"
        response.headers["X-Kaira-DB-Mode"] = getattr(
            getattr(request, "app", None), "state", None
        ) and getattr(request.app.state, "db_mode", "online") or "online"

        if not quiet:
            http(
                request.method,
                path,
                response.status_code,
                duration_ms,
                request_id,
                client=_client_host(request),
            )
        return response


def register_framework_exception_handlers(app: Any) -> None:
    """Register global exception handlers ensuring the unified error contract."""
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    try:
        from slowapi.errors import RateLimitExceeded
    except ImportError:  # pragma: no cover
        RateLimitExceeded = None  # type: ignore[misc,assignment]

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = _field_errors(exc)
        shown = fields[:8]
        rows = [(row["field"], row["message"]) for row in shown]
        if len(fields) > len(shown):
            rows.append(("…", f"{len(fields) - len(shown)} more field(s)"))

        logger.warning(
            f"{request.method} {request.url.path} rejected — "
            f"{len(fields)} invalid field(s)"
            + detail(*rows, request=_request_id(request))
        )
        return _error_response(
            request,
            422,
            "validation_error",
            f"Request validation failed for {len(fields)} field(s).",
            detail_value=jsonable_encoder(exc.errors()),
            fields=fields,
        )

    if RateLimitExceeded is not None:
        @app.exception_handler(RateLimitExceeded)
        async def rate_limit_handler(request: Request, exc: Any) -> JSONResponse:
            limit = getattr(exc, "detail", "") or "rate limit"
            logger.warning(
                f"{request.method} {request.url.path} rate limited"
                + detail(
                    limit=limit,
                    client=_client_host(request),
                    request=_request_id(request),
                )
            )
            return _error_response(
                request,
                429,
                "rate_limited",
                "Too many requests. Please slow down.",
                extra={"limit": str(limit)},
            )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if exc.status_code >= 500:
            logger.error(
                f"{request.method} {request.url.path} failed with {exc.status_code}"
                + detail(reason=message, request=_request_id(request))
            )
        else:
            logger.debug(
                f"{request.method} {request.url.path} -> {exc.status_code}: {message}"
            )
        return _error_response(
            request,
            exc.status_code,
            "http_error",
            message,
            detail_value=exc.detail,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        from kaira.app.exceptions import KairaError, LayerViolationError

        if isinstance(exc, LayerViolationError):
            raise exc
        if isinstance(exc, KairaError):
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        _log_unhandled(request, exc)
        extra = (
            {"exception": type(exc).__name__, "reason": str(exc)}
            if _EXPOSE_INTERNALS
            else None
        )
        return _error_response(
            request,
            500,
            "internal_error",
            "An internal error occurred. Please try again later.",
            extra=extra,
        )


__all__ = [
    "ObservabilityMiddleware",
    "register_framework_exception_handlers",
]
