"""Provider base interface for framework extensions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class KairaProvider(ABC):
    """Abstract base class for all built-in and third-party Kaira providers."""

    name: str = "base"

    @abstractmethod
    def register(self, app: Any) -> None:
        """Register provider state, routes, dependencies, or middleware with the app."""
        pass

    async def startup(self) -> None:
        """Lifecycle hook executed on app startup (e.g. establishing pool connections)."""
        pass

    async def shutdown(self) -> None:
        """Lifecycle hook executed on app shutdown (e.g. closing sockets/pools)."""
        pass
