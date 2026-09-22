"""Dependency Injection container for Enterprise Tier architecture."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class Container:
    """Lightweight service registry and dependency container."""

    def __init__(self) -> None:
        self._singletons: dict[Any, Any] = {}
        self._factories: dict[Any, Callable[[], Any]] = {}

    def register_singleton(self, key: Any, instance: Any) -> None:
        """Register a pre-instantiated singleton instance."""
        self._singletons[key] = instance

    def register_factory(self, key: Any, factory: Callable[[], Any]) -> None:
        """Register a factory callable to construct instances on-demand."""
        self._factories[key] = factory

    def resolve(self, key: type[T] | str) -> T:
        """Resolve a service by class type or string identifier."""
        if key in self._singletons:
            return self._singletons[key]  # type: ignore[no-any-return]
        if key in self._factories:
            return self._factories[key]()  # type: ignore[no-any-return]
        raise KeyError(f"Service '{key}' is not registered in the DI container.")
