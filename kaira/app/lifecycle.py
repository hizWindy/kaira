"""Lifecycle management — startup/shutdown hooks and event system."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class LifecycleManager:
    """Manages application lifecycle events (startup, shutdown, per-request)."""

    def __init__(self) -> None:
        self._startup_hooks: list[Callable[[], Any]] = []
        self._shutdown_hooks: list[Callable[[], Any]] = []
        self._request_hooks: list[Callable[[Any], Any]] = []

    def on_startup(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Register a hook to run on app startup."""
        self._startup_hooks.append(func)
        return func

    def on_shutdown(self, func: Callable[[], Any]) -> Callable[[], Any]:
        """Register a hook to run on app shutdown."""
        self._shutdown_hooks.append(func)
        return func

    def add_request_hook(self, func: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """Register a hook to run on each request."""
        self._request_hooks.append(func)
        return func

    async def run_startup(self) -> None:
        """Execute all registered startup hooks."""
        for hook in self._startup_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook()
            else:
                hook()

    async def run_shutdown(self) -> None:
        """Execute all registered shutdown hooks."""
        for hook in self._shutdown_hooks:
            if inspect.iscoroutinefunction(hook):
                await hook()
            else:
                hook()
