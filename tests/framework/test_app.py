"""Tests for KairaApp instantiation, auto-registration, and routing."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient

from kaira.app.kaira_app import KairaApp
from kaira.app.providers.base import KairaProvider


def test_kaira_app_is_fastapi_subclass() -> None:
    app = KairaApp(project_name="testapp", auto_register=False)
    assert isinstance(app, FastAPI)
    assert app.project_name == "testapp"
    assert app.tier == "standard"


def test_kaira_app_explicit_router_registration() -> None:
    app = KairaApp(project_name="testapp", auto_register=False)
    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict[str, str]:
        return {"ping": "pong"}

    app.register_router(router, prefix="/api")

    client = TestClient(app)
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ping": "pong"}


def test_kaira_app_security_headers_middleware() -> None:
    app = KairaApp(project_name="secapp", auto_register=False)

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"hello": "world"}

    client = TestClient(app)
    resp = client.get("/hello")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in resp.headers


def test_kaira_app_custom_provider_registration() -> None:
    app = KairaApp(project_name="provapp", auto_register=False, providers=[])

    class DummyProvider(KairaProvider):
        name = "dummy"

        def __init__(self) -> None:
            self.registered = False

        def register(self, app_instance: KairaApp) -> None:
            self.registered = True
            app_instance.state.dummy = "active"

    prov = DummyProvider()
    app.register_provider(prov)
    assert prov.registered is True
    assert app.state.dummy == "active"
    assert prov in app.providers
