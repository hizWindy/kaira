"""Rate limiting middleware and limiter integration."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Callable, Dict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class InMemoryLimiter:
    """Fallback in-memory rate limiter when Redis/slowapi is not active."""

    def __init__(self, limit: int = 100, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._history: Dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        records = [ts for ts in self._history[key] if ts > window_start]
        if len(records) >= self.limit:
            return False
        records.append(now)
        self._history[key] = records
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces request limits per client IP."""

    def __init__(
        self, app: Any, default_limit: int = 120, window_seconds: int = 60
    ) -> None:
        super().__init__(app)
        self.limiter = InMemoryLimiter(
            limit=default_limit, window_seconds=window_seconds
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not self.limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )
        return await call_next(request)  # type: ignore[no-any-return]
