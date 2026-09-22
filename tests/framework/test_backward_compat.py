"""Tests for backward compatibility with legacy Kaira projects."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient

from kaira.config import KairaConfig


def test_legacy_kaira_config_deserialization() -> None:
    # Simulates old .kaira.json without Phase 8 fields
    legacy_json = {
        "output_dir": ".",
        "db_type": "sqlite",
        "api_version": "v1",
        "auth_type": "jwt",
        "generated_models": [{"name": "Item", "fields": [], "relations": []}],
    }
    cfg = KairaConfig.from_dict(legacy_json)
    assert cfg.db_type == "sqlite"
    assert cfg.tier == "standard"
    assert cfg.kaira_version in ("0.2.0", "0.2.3", "0.2.4")
    assert cfg.enforce_layers is True
    assert cfg.auto_register is True


def test_legacy_fastapi_app_interoperability() -> None:
    # A legacy app using standard FastAPI
    app = FastAPI(title="LegacyApp")

    @app.get("/items")
    def list_items() -> dict[str, list[str]]:
        return {"items": ["item1", "item2"]}

    client = TestClient(app)
    resp = client.get("/items")
    assert resp.status_code == 200
    assert resp.json() == {"items": ["item1", "item2"]}
