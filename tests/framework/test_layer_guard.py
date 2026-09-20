"""Tests for 5-layer pipeline runtime enforcement."""

from __future__ import annotations

import pytest
from pathlib import Path
from starlette.testclient import TestClient

from kaira.app.exceptions import LayerViolationError
from kaira.app.kaira_app import KairaApp
from kaira.app.middleware.layer_guard import audit_router_ast


def test_audit_clean_router(tmp_path: Path) -> None:
    clean_router = tmp_path / "user_router.py"
    clean_router.write_text(
        """
from fastapi import APIRouter, Depends
from services.user_service import UserService

router = APIRouter()

@router.get("/users")
def list_users(service: UserService = Depends()):
    return service.get_all()
""",
        encoding="utf-8",
    )
    violations = audit_router_ast(clean_router)
    assert violations == []


def test_audit_violating_router(tmp_path: Path) -> None:
    bad_router = tmp_path / "order_router.py"
    bad_router.write_text(
        """
from fastapi import APIRouter
from repositories.order_repository import OrderRepository

router = APIRouter()
""",
        encoding="utf-8",
    )
    violations = audit_router_ast(bad_router)
    assert len(violations) == 1
    assert "Direct 'from repositories.order_repository'" in violations[0]


def test_layer_guard_middleware_enforcement(tmp_path: Path) -> None:
    # Create a violating router in a temporary directory
    routers_dir = tmp_path / "routers"
    routers_dir.mkdir()
    bad_router = routers_dir / "bad_router.py"
    bad_router.write_text(
        "from repositories.sample_repository import SampleRepository\n",
        encoding="utf-8",
    )

    app = KairaApp(
        project_name="layerapp",
        auto_register=False,
        enforce_layers=True,
        routers_dir=routers_dir,
    )

    client = TestClient(app)
    # The first request triggers layer guard audit and fails
    with pytest.raises(LayerViolationError):
        client.get("/health")
