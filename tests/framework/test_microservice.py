"""Tests for microservice decomposition."""

from __future__ import annotations

from pathlib import Path

import pytest

from kaira.commands.project import microservice_split_command


def test_microservice_split_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")

    # Set up a monolith directory structure
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "user.py").write_text("class User: pass\n", encoding="utf-8")

    routers_dir = tmp_path / "routers"
    routers_dir.mkdir()
    (routers_dir / "user_router.py").write_text(
        "from fastapi import APIRouter; router = APIRouter()\n", encoding="utf-8"
    )

    # Run microservice split
    microservice_split_command(service_name="user_service", models=["User"])

    svc_dir = tmp_path / "user_service"
    assert svc_dir.exists()
    assert (svc_dir / "main.py").exists()
    assert (svc_dir / ".kaira.json").exists()
    assert (svc_dir / "models" / "user.py").exists()
    assert (svc_dir / "routers" / "user_router.py").exists()
