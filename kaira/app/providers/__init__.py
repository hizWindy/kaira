"""Framework provider registry and exports."""

from __future__ import annotations

from typing import Dict, Type

from kaira.app.providers.auth import AuthProvider
from kaira.app.providers.base import KairaProvider
from kaira.app.providers.cache import CacheProvider
from kaira.app.providers.monitor import MonitorProvider
from kaira.app.providers.task import TaskProvider

_PROVIDER_REGISTRY: Dict[str, Type[KairaProvider]] = {
    "cache": CacheProvider,
    "auth": AuthProvider,
    "monitor": MonitorProvider,
    "task": TaskProvider,
}


def get_provider(name: str) -> KairaProvider:
    """Instantiate a registered provider by name."""
    provider_cls = _PROVIDER_REGISTRY.get(name.lower())
    if not provider_cls:
        raise KeyError(
            f"Unknown provider '{name}'. Registered providers: {list(_PROVIDER_REGISTRY.keys())}"
        )
    return provider_cls()


def register_provider_type(name: str, provider_cls: Type[KairaProvider]) -> None:
    """Register a custom or third-party provider type."""
    _PROVIDER_REGISTRY[name.lower()] = provider_cls


__all__ = [
    "KairaProvider",
    "CacheProvider",
    "AuthProvider",
    "MonitorProvider",
    "TaskProvider",
    "get_provider",
    "register_provider_type",
]
