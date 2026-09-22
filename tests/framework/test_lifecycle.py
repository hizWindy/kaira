"""Tests for LifecycleManager startup and shutdown hooks."""

from __future__ import annotations

import pytest

from kaira.app.lifecycle import LifecycleManager


def test_lifecycle_startup_and_shutdown_hooks() -> None:
    import anyio

    async def _test() -> None:
        lifecycle = LifecycleManager()
        events: list[str] = []

        @lifecycle.on_startup
        async def async_boot() -> None:
            events.append("async_boot")

        @lifecycle.on_startup
        def sync_boot() -> None:
            events.append("sync_boot")

        @lifecycle.on_shutdown
        async def async_cleanup() -> None:
            events.append("async_cleanup")

        @lifecycle.on_shutdown
        def sync_cleanup() -> None:
            events.append("sync_cleanup")

        assert events == []

        await lifecycle.run_startup()
        assert events == ["async_boot", "sync_boot"]

        await lifecycle.run_shutdown()
        assert events == ["async_boot", "sync_boot", "async_cleanup", "sync_cleanup"]

    anyio.run(_test)
