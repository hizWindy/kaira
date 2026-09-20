"""Dependency injection helpers for Khaira Framework applications."""

from __future__ import annotations

from typing import Any, Callable, Type, TypeVar
from fastapi import Depends

T = TypeVar("T")


def inject(factory: Callable[..., T]) -> Any:
    """Type-safe dependency injection helper wrapping FastAPI Depends."""
    return Depends(factory)


def service_dependency(service_cls: Type[T]) -> Callable[..., T]:
    """Helper to construct a dependency provider for service layer classes."""

    def _provide_service(*args: Any, **kwargs: Any) -> T:
        return service_cls(*args, **kwargs)

    return _provide_service
