"""Tests for Kaira runtime, KairaApp behavior, router discovery, and endpoints."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from kaira.app.kaira_app import KairaApp


def test_kaira_app_default_endpoints() -> None:
    app = KairaApp(project_name="my-app", auto_register=False)
    client = TestClient(app)

    # Test GET /
    root_resp = client.get("/")
    assert root_resp.status_code == 200
    root_data = root_resp.json()
    assert root_data["status"] == "online"
    assert root_data["app"] == "my-app"

    # Test GET /health
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "ok"
    assert health_data["app"] == "my-app"
    assert "database" in health_data


def test_kaira_app_router_prefix_handling(tmp_path: Path) -> None:
    """Test that routers with existing prefix (e.g. /users) are mounted under /api/v1 without double prefix."""
    routers_dir = tmp_path / "routers"
    routers_dir.mkdir(parents=True)

    # Router file with prefix="/users"
    router_code = (
        "from fastapi import APIRouter\n"
        'router = APIRouter(prefix="/users")\n'
        '@router.get("")\n'
        'def list_users(): return [{"id": 1}]\n'
    )
    (routers_dir / "user_router.py").write_text(router_code, encoding="utf-8")

    app = KairaApp(project_name="prefix-app", auto_register=True, routers_dir=routers_dir)
    client = TestClient(app)

    # Should be reachable at /api/v1/users
    resp = client.get("/api/v1/users")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1}]

    # Should NOT be reachable at double prefix /user/users
    bad_resp = client.get("/user/users")
    assert bad_resp.status_code == 404


def test_kaira_app_lifecycle_hooks() -> None:
    app = KairaApp(project_name="hook-app", auto_register=False)
    hook_events = []

    @app.on_startup
    def startup_hook() -> None:
        hook_events.append("started")

    @app.on_shutdown
    def shutdown_hook() -> None:
        hook_events.append("stopped")

    with TestClient(app):
        assert "started" in hook_events
    assert "stopped" in hook_events


def test_kaira_app_observability_headers() -> None:
    """ObservabilityMiddleware must inject X-Request-ID and X-Response-Time headers."""
    app = KairaApp(project_name="obs-app", auto_register=False)
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) == 8
    assert "x-response-time" in resp.headers
    assert "ms" in resp.headers["x-response-time"]


def test_kaira_app_validation_error_contract() -> None:
    """Request validation errors return standard 422 envelope with field list."""
    from pydantic import BaseModel

    class Item(BaseModel):
        name: str
        price: float

    app = KairaApp(project_name="val-app", auto_register=False)

    @app.post("/items")
    def create_item(item: Item):
        return item

    client = TestClient(app)
    resp = client.post("/items", json={"price": "not-a-number"})
    assert resp.status_code == 422
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["status"] == 422
    assert "fields" in body["error"]
    assert "x-request-id" in resp.headers


def test_kaira_app_logging_exports() -> None:
    """Verify detail, http, logger, and status_style are accessible from kaira.app.logging."""
    from kaira.app.logging import detail, http, logger, status_style

    assert callable(detail)
    assert callable(http)
    assert callable(status_style)
    assert logger is not None
    assert status_style(200) == "green"
    assert status_style(404) == "yellow"
    assert status_style(500) == "red"

    det = detail(env="test", mode="online")
    assert "env" in det
    assert "online" in det

