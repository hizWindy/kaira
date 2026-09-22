"""Tests for built-in providers: Cache, Auth, Monitor, and Task."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from kaira.app.kaira_app import KairaApp
from kaira.app.providers import (
    AuthProvider,
    CacheProvider,
    MonitorProvider,
    TaskProvider,
    get_provider,
)


def test_cache_provider_in_memory() -> None:
    import anyio

    async def _test() -> None:
        cache = CacheProvider()
        await cache.startup()

        await cache.set("greeting", "hello", expire=60)
        val = await cache.get("greeting")
        assert val == "hello"

        await cache.delete("greeting")
        assert await cache.get("greeting") is None

        await cache.set("k1", "v1")
        await cache.set("k2", "v2")
        await cache.clear()
        assert await cache.get("k1") is None
        assert await cache.get("k2") is None

        await cache.shutdown()

    anyio.run(_test)


def test_auth_provider_password_and_jwt() -> None:
    auth = AuthProvider(secret_key="test-secret-key-that-is-at-least-32-chars-long")

    hashed = auth.hash_password("SuperSecret123!")
    assert hashed != "SuperSecret123!"
    assert auth.verify_password("SuperSecret123!", hashed) is True
    assert auth.verify_password("WrongPassword!", hashed) is False

    token = auth.create_token({"sub": "user_42", "role": "admin"})
    assert isinstance(token, str)

    payload = auth.verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user_42"
    assert payload["role"] == "admin"


def test_monitor_provider_probes() -> None:
    app = KairaApp(project_name="monapp", auto_register=False, providers=[])
    monitor = MonitorProvider()
    app.register_provider(monitor)

    client = TestClient(app)
    resp_live = client.get("/healthz")
    assert resp_live.status_code == 200
    assert resp_live.json() == {"status": "live"}

    resp_ready = client.get("/readyz")
    assert resp_ready.status_code == 200
    assert resp_ready.json() == {"status": "ready"}

    resp_metrics = client.get("/metrics")
    assert resp_metrics.status_code == 200


def test_task_provider_decorator() -> None:
    task_prov = TaskProvider()

    @task_prov.task()
    def sample_job(x: int, y: int) -> int:
        return x + y

    assert sample_job(3, 4) == 7


def test_provider_registry_get_provider() -> None:
    p_cache = get_provider("cache")
    assert isinstance(p_cache, CacheProvider)

    p_auth = get_provider("auth")
    assert isinstance(p_auth, AuthProvider)

    p_mon = get_provider("monitor")
    assert isinstance(p_mon, MonitorProvider)

    p_task = get_provider("task")
    assert isinstance(p_task, TaskProvider)

    with pytest.raises(KeyError):
        get_provider("non_existent_provider")
