"""Rate limiting abstraction module for Khaira framework."""

from __future__ import annotations

from kaira.app.middleware.rate_limit import InMemoryLimiter, RateLimitMiddleware

try:
    from slowapi import Limiter as _SlowapiLimiter  # type: ignore[import-untyped]
    from slowapi.util import (
        get_remote_address as _get_remote_address,  # type: ignore[import-untyped]
    )

    Limiter = _SlowapiLimiter
    get_remote_address = _get_remote_address
    limiter = Limiter(key_func=get_remote_address)
except ImportError:
    Limiter = InMemoryLimiter  # type: ignore[misc,assignment]
    get_remote_address = None  # type: ignore[assignment,misc]
    limiter = InMemoryLimiter()  # type: ignore[misc,assignment]

# Common alias
RateLimiter = Limiter

__all__ = [
    "InMemoryLimiter",
    "Limiter",
    "RateLimitMiddleware",
    "RateLimiter",
    "get_remote_address",
    "limiter",
]
