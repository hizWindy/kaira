"""Rate limiting abstraction module for Khaira framework."""

from __future__ import annotations

from kaira.app.middleware.rate_limit import InMemoryLimiter, RateLimitMiddleware

try:
    from slowapi import Limiter as _SlowapiLimiter  # type: ignore[import-untyped]
    Limiter = _SlowapiLimiter
except ImportError:
    Limiter = InMemoryLimiter  # type: ignore[misc,assignment]

# Common alias
RateLimiter = Limiter

__all__ = [
    "Limiter",
    "RateLimiter",
    "InMemoryLimiter",
    "RateLimitMiddleware",
]
