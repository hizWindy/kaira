"""Structured logging setup for Khaira Framework applications.

One sink, one format, one timestamp style. A Loguru ``InterceptHandler``
captures the stdlib loggers that FastAPI/Uvicorn write to — ``uvicorn``,
``uvicorn.access``, ``uvicorn.error``, ``watchfiles`` and ``sqlalchemy.engine``
— so they no longer collide with Loguru or print in three different styles.
All output goes to stdout only; there are no log files.
"""

from __future__ import annotations

import json
import logging
import os
import sys

try:
    from loguru import logger as _loguru_logger

    _HAS_LOGURU = True
except ImportError:  # pragma: no cover
    _HAS_LOGURU = False

# ── Runtime configuration ────────────────────────────────────────────────────

LOG_LEVEL = os.getenv("KAIRA_LOG_LEVEL", "INFO").upper()
APP_ENV = os.getenv("APP_ENV", "development")
LOG_FORMAT = os.getenv("KAIRA_LOG_FORMAT", "text").strip().lower()

JSON_LOGS = LOG_FORMAT == "json"

_ACCESS_LOG = os.getenv("KAIRA_ACCESS_LOG") == "1"
_COLOR = (
    bool(getattr(sys.stdout, "isatty", lambda: False)()) or bool(os.getenv("FORCE_COLOR"))
) and not os.getenv("NO_COLOR")
_UTF8 = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()

_diagnose_env = os.getenv("KAIRA_DIAGNOSE")
DIAGNOSE = (
    _diagnose_env == "1" if _diagnose_env is not None else APP_ENV != "production"
)


def is_debug() -> bool:
    """Return True when the sink is printing DEBUG/TRACE records."""
    return LOG_LEVEL in ("DEBUG", "TRACE")


# ── Alignment & glyphs ───────────────────────────────────────────────────────

_LEVEL_WIDTH = 8
INDENT = " " * (8 + 2 + _LEVEL_WIDTH + 2)  # 20 columns

_TREE_MID, _TREE_END = ("├─ ", "└─ ") if _UTF8 else ("|- ", "`- ")
_DOT = "·" if _UTF8 else "-"
SEPARATOR = f" {_DOT} "

_LEVEL_STYLE = {
    "TRACE": "light-black",
    "DEBUG": "light-black",
    "INFO": "cyan",
    "SUCCESS": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "light-red",
}

_MESSAGE_STYLE = {
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold light-red",
}


def status_style(status: int) -> str:
    """Return the Loguru colour tag name for an HTTP status code."""
    if status >= 500:
        return "red"
    if status >= 400:
        return "yellow"
    if status >= 300:
        return "cyan"
    return "green"


def _duration_style(duration_ms: float) -> str:
    """Dim for a fast response, tinted once it is worth noticing."""
    if duration_ms >= 1500:
        return "red"
    if duration_ms >= 500:
        return "yellow"
    return "light-black"


# ── Detail blocks ────────────────────────────────────────────────────────────


def detail(*pairs: tuple[str, object], **rows: object) -> str:
    """Render aligned continuation lines to append to a log message."""
    items: list[tuple[str, object]] = [(str(k), v) for k, v in pairs]
    items += [(k.replace("_", " "), v) for k, v in rows.items()]
    if not items:
        return ""

    width = max(len(label) for label, _ in items)
    lines = []
    for index, (label, value) in enumerate(items):
        glyph = _TREE_END if index == len(items) - 1 else _TREE_MID
        lines.append("\n" + INDENT + glyph + label.ljust(width) + "  " + str(value))
    return "".join(lines)


# ── Formatter ────────────────────────────────────────────────────────────────


def _http_body(extra: dict) -> str:
    """Build the colourised body of a request-completion line."""
    status = int(extra.get("status", 0))
    duration = float(extra.get("duration_ms", 0.0))
    s_style = status_style(status)
    d_style = _duration_style(duration)

    body = (
        "<bold>{extra[method]: <7}</bold>"
        "<" + s_style + ">{extra[status]}</" + s_style + ">  "
        "{extra[path]}"
        "  <light-black>" + _DOT + "</light-black>  "
        "<" + d_style + ">{extra[duration_ms]:.1f}ms</" + d_style + ">"
    )
    if extra.get("show_id"):
        body += (
            "  <light-black>" + _DOT + " req {extra[request_id]}</light-black>"
        )
    return body


_JSON_RESERVED = {"kaira_http", "show_id"}


def _json_line(record: dict) -> str:
    """Render one record as a single-line JSON object on stdout."""
    extra = record["extra"]
    payload: dict = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "logger": record["name"],
    }

    if extra.get("kaira_http"):
        payload["event"] = "request"
        payload["method"] = extra.get("method")
        payload["path"] = extra.get("path")
        payload["status"] = extra.get("status")
        payload["duration_ms"] = round(float(extra.get("duration_ms", 0.0)), 2)
        payload["request_id"] = extra.get("request_id")
        payload["client"] = extra.get("client")

    for key, value in extra.items():
        if key not in _JSON_RESERVED and key not in payload:
            payload[key] = value

    exception = record.get("exception")
    if exception is not None:
        payload["exception"] = {
            "type": getattr(exception.type, "__name__", str(exception.type)),
            "value": str(exception.value),
        }

    return json.dumps(payload, default=str) + "\n"


def _formatter(record: dict) -> str:
    """Return the Loguru format string for a single record."""
    level_name = record["level"].name
    level_style = _LEVEL_STYLE.get(level_name, "white")

    parts = [
        "<light-black>{time:HH:mm:ss}</light-black>  ",
        "<" + level_style + ">{level: <" + str(_LEVEL_WIDTH) + "}</" + level_style + ">  ",
    ]

    if record["extra"].get("kaira_http"):
        parts.append(_http_body(record["extra"]))
    else:
        message_style = _MESSAGE_STYLE.get(level_name)
        if message_style:
            parts.append("<" + message_style + ">{message}</" + message_style + ">")
        else:
            parts.append("{message}")

    parts.append("\n{exception}")
    return "".join(parts)


# ── Initialize Loguru sink ───────────────────────────────────────────────────

if _HAS_LOGURU:
    logger = _loguru_logger
    logger.remove()

    def _json_sink(message: object) -> None:
        sys.stdout.write(_json_line(message.record))  # type: ignore[attr-defined]

    if JSON_LOGS:
        logger.add(
            _json_sink,
            level=LOG_LEVEL,
            enqueue=True,
            backtrace=is_debug(),
            diagnose=False,
        )
    else:
        logger.add(
            sys.stdout,
            format=_formatter,
            level=LOG_LEVEL,
            colorize=_COLOR,
            enqueue=True,
            backtrace=is_debug(),
            diagnose=DIAGNOSE,
        )
else:  # pragma: no cover - fallback when loguru is not installed
    logger = logging.getLogger("kaira")


# ── Request logging ──────────────────────────────────────────────────────────


def http(
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    request_id: str,
    client: str | None = None,
) -> None:
    """Log one completed request as a single, status-coloured line."""
    if status >= 500:
        level = "ERROR"
    elif status >= 400:
        level = "WARNING"
    else:
        level = "INFO"

    show_id = status >= 400 or is_debug()

    if _HAS_LOGURU:
        bound = logger.bind(
            kaira_http=True,
            method=method,
            path=path,
            status=status,
            duration_ms=duration_ms,
            request_id=request_id,
            client=client or "unknown",
            show_id=show_id,
        )
        bound.log(level, f"{method} {status} {path} {duration_ms:.1f}ms")
    else:  # pragma: no cover
        logger.log(
            getattr(logging, level, logging.INFO),
            f"{method} {status} {path} {duration_ms:.1f}ms (req: {request_id})",
        )


# ── stdlib bridge ────────────────────────────────────────────────────────────

_DEMOTED_PREFIXES = (
    "Started server process",
    "Started reloader process",
    "Waiting for application startup",
    "Application startup complete",
    "Waiting for application shutdown",
    "Application shutdown complete",
    "Finished server process",
    "Stopping reloader process",
    "Will watch for changes in these directories",
    "Uvicorn running on",
    "Exception in ASGI application",
)


class InterceptHandler(logging.Handler):
    """Route stdlib ``logging`` records into Loguru's single sink."""

    def emit(self, record: logging.LogRecord) -> None:
        if not _HAS_LOGURU:  # pragma: no cover
            return

        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        message = record.getMessage()

        if (
            record.name.startswith("uvicorn")
            or record.name.startswith("watchfiles")
            or record.name.startswith("httpx")
            or record.name.startswith("httpcore")
        ) and (
            any(message.startswith(prefix) for prefix in _DEMOTED_PREFIXES)
            or message.startswith("HTTP Request:")
        ):
            level = "DEBUG"

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, message)


def configure_intercept(sql_echo: bool = False) -> None:
    """Redirect the noisy stdlib loggers into Loguru's single sink."""
    intercept = InterceptHandler()
    root_level = logging.DEBUG if is_debug() else logging.INFO
    logging.basicConfig(handlers=[intercept], level=root_level, force=True)

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        std = logging.getLogger(name)
        std.handlers = [intercept]
        std.propagate = False

    if not _ACCESS_LOG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    sa = logging.getLogger("sqlalchemy.engine")
    sa.handlers = [intercept]
    sa.propagate = False
    sa.setLevel(logging.INFO if sql_echo else logging.WARNING)

    for name in (
        "watchfiles",
        "watchfiles.main",
        "pymongo",
        "motor",
        "asyncio",
        "httpx",
        "httpcore",
    ):
        noisy = logging.getLogger(name)
        noisy.handlers = [intercept]
        noisy.propagate = False
        noisy.setLevel(logging.WARNING)


# Configure intercept by default on module load
configure_intercept(sql_echo=os.getenv("KAIRA_SQL_ECHO") == "1")

__all__ = [
    "INDENT",
    "JSON_LOGS",
    "LOG_FORMAT",
    "LOG_LEVEL",
    "SEPARATOR",
    "InterceptHandler",
    "configure_intercept",
    "detail",
    "http",
    "is_debug",
    "logger",
    "status_style",
]
