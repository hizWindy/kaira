"""Security headers middleware for Khaira Framework applications."""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds hardened security headers to all responses."""

    def __init__(
        self,
        app: Any,
        content_security_policy: str = "default-src 'self'",
        frame_options: str = "DENY",
        hsts_max_age: int = 31536000,
    ) -> None:
        super().__init__(app)
        self.csp = content_security_policy
        self.frame_options = frame_options
        self.hsts = f"max-age={hsts_max_age}; includeSubDomains"

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = self.frame_options
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = self.hsts
        response.headers["Content-Security-Policy"] = self.csp
        return response
