"""Framework middleware components."""

from __future__ import annotations

from kaira.app.middleware.base import BaseHTTPMiddleware
from kaira.app.middleware.cors import create_cors_middleware
from kaira.app.middleware.layer_guard import LayerGuardMiddleware, audit_layers
from kaira.app.middleware.observability import (
    ObservabilityMiddleware,
    register_framework_exception_handlers,
)
from kaira.app.middleware.rate_limit import RateLimitMiddleware
from kaira.app.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "BaseHTTPMiddleware",
    "LayerGuardMiddleware",
    "ObservabilityMiddleware",
    "RateLimitMiddleware",
    "SecurityHeadersMiddleware",
    "audit_layers",
    "create_cors_middleware",
    "register_framework_exception_handlers",
]
