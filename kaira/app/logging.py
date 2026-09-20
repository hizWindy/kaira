"""Structured logging setup for Khaira Framework applications."""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict

try:
    from loguru import logger as _loguru_logger

    _HAS_LOGURU = True
except ImportError:
    _HAS_LOGURU = False


class JSONFormatter(logging.Formatter):
    """Simple structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging(json_format: bool = False, level: str = "INFO") -> logging.Logger:
    """Configure and return the root Kaira framework logger."""
    logger = logging.getLogger("kaira")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
        )
    logger.addHandler(handler)
    return logger


if _HAS_LOGURU:
    logger = _loguru_logger
else:
    logger = setup_logging()

__all__ = ["logger", "setup_logging", "JSONFormatter"]
