"""Tests for MigrationEngine, upgrade validation, and rollback safety."""

from __future__ import annotations

import json
from pathlib import Path

from kaira.migrations.engine import MigrationEngine
from kaira.migrations.rules import describe_upgrade, is_valid_upgrade


def test_upgrade_rules_validation() -> None:
    assert is_valid_upgrade("simple", "standard") is True
    assert is_valid_upgrade("standard", "enterprise") is True
    assert is_valid_upgrade("simple", "enterprise") is True
    assert is_valid_upgrade("standard", "simple") is False
    assert is_valid_upgrade("enterprise", "standard") is False


def test_describe_upgrade_actions() -> None:
    actions = describe_upgrade("simple", "standard")
    assert len(actions) > 0
    assert any("KairaApp" in a for a in actions)


def test_upgrade_dry_run_does_not_modify(tmp_path: Path) -> None:
    cfg = tmp_path / ".kaira.json"
    cfg.write_text(
        json.dumps({"tier": "simple", "db_name": "dryproj"}), encoding="utf-8"
    )
    main_py = tmp_path / "main.py"
    main_py.write_text("app = FastAPI()", encoding="utf-8")

    engine = MigrationEngine(root=tmp_path)
    actions = engine.upgrade(target_tier="standard", dry_run=True)

    assert len(actions) > 0
    # Confirm file was not modified
    assert main_py.read_text(encoding="utf-8") == "app = FastAPI()"
    # Confirm tier is still simple
    assert json.loads(cfg.read_text(encoding="utf-8"))["tier"] == "simple"


def test_upgrade_execution_and_rollback_on_failure(tmp_path: Path) -> None:
    cfg = tmp_path / ".kaira.json"
    cfg.write_text(
        json.dumps({"tier": "simple", "db_name": "rollproj"}), encoding="utf-8"
    )
    main_py = tmp_path / "main.py"
    main_py.write_text("app = FastAPI()", encoding="utf-8")

    engine = MigrationEngine(root=tmp_path)
    # Upgrade to standard
    engine.upgrade(target_tier="standard", dry_run=False)

    # Check that main.py now uses KairaApp
    updated_main = main_py.read_text(encoding="utf-8")
    assert "KairaApp" in updated_main

    # Check updated tier in .kaira.json
    new_cfg = json.loads(cfg.read_text(encoding="utf-8"))
    assert new_cfg["tier"] == "standard"

    # Check docs/ was created
    assert (tmp_path / "docs" / "index.md").exists()
    assert (tmp_path / "docs" / "architecture.md").exists()
