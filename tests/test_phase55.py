"""Tests for Phase 5.5 — fixes, env audit/prune, and sync model cascade.

Covers:
- FIX 1  credential masking in DB error output (regression)
- FIX 3  migrate short-circuit on MongoDB / Firestore
- FIX 4  AST-based settings.py parsing
- FEATURE A  env audit / env prune
- kaira sync model  per-layer cascade
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kaira.main import app

runner = CliRunner()


@pytest.fixture()
def project(tmp_path, monkeypatch):
    """Chdir into an empty temp project directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_config(path: Path, **overrides) -> None:
    data = {
        "db_type": "sqlite",
        "output_dir": ".",
        "auth_type": "none",
        "generated_models": [],
    }
    data.update(overrides)
    (path / ".kaira.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# FIX 1 — credential masking in error output
# ---------------------------------------------------------------------------


class TestCredentialMasking:
    def test_password_masked_in_connection_error(self, project, monkeypatch):
        _write_config(project, db_type="postgresql")
        secret = "sup3rs3cr3t"
        url = f"postgresql+asyncpg://admin:{secret}@10.0.0.9:5432/prod"
        monkeypatch.setenv("DATABASE_URL", url)

        # Force the real login check to raise an error embedding the DSN.
        from kaira.commands import db_cmd

        def _boom(db_type, raw_url):
            return False, f"auth failed for {raw_url}"

        monkeypatch.setattr(db_cmd, "_test_connection_real", _boom)

        result = runner.invoke(app, ["db", "connect"])
        assert result.exit_code == 1
        assert secret not in result.output
        assert "***" in result.output

    def test_mask_credentials_handles_asyncpg_scheme(self):
        from kaira.commands.ux_helpers import mask_credentials

        masked = mask_credentials("postgresql+asyncpg://user:pw123@host:5432/db")
        assert "pw123" not in masked


# ---------------------------------------------------------------------------
# FIX 3 — migrate guard on document databases
# ---------------------------------------------------------------------------


class TestMigrateGuard:
    @pytest.mark.parametrize("db_type", ["mongodb", "atlas", "firebase", "firestore"])
    def test_migrate_make_blocked(self, project, db_type):
        _write_config(project, db_type=db_type)
        result = runner.invoke(app, ["migrate", "make", "x"])
        assert result.exit_code == 1
        assert "not supported" in result.output

    def test_migrate_run_blocked_on_firebase(self, project):
        _write_config(project, db_type="firebase")
        result = runner.invoke(app, ["migrate", "run"])
        assert result.exit_code == 1

    def test_relational_db_not_blocked_by_guard(self, project):
        # sqlite should pass the guard (it may still fail later on missing alembic,
        # but the guard itself must not raise the "not supported" error).
        _write_config(project, db_type="sqlite")
        from kaira.commands.migrate import _guard_relational_db

        _guard_relational_db()  # should not raise


# ---------------------------------------------------------------------------
# FIX 4 — AST settings parsing
# ---------------------------------------------------------------------------


class TestSettingsAstParsing:
    def test_annotated_class_attribute(self, tmp_path):
        settings = tmp_path / "settings.py"
        settings.write_text(
            "class Settings:\n    DATABASE_URL: str = 'sqlite+aiosqlite:///./app.db'\n",
            encoding="utf-8",
        )
        from kaira.commands.db_cmd import _extract_setting_default

        assert _extract_setting_default(settings, "DATABASE_URL") == (
            "sqlite+aiosqlite:///./app.db"
        )

    def test_plain_module_assignment(self, tmp_path):
        settings = tmp_path / "settings.py"
        settings.write_text('DATABASE_URL = "postgresql://x"\n', encoding="utf-8")
        from kaira.commands.db_cmd import _extract_setting_default

        assert _extract_setting_default(settings, "DATABASE_URL") == "postgresql://x"

    def test_missing_key_returns_none(self, tmp_path):
        settings = tmp_path / "settings.py"
        settings.write_text("OTHER = 1\n", encoding="utf-8")
        from kaira.commands.db_cmd import _extract_setting_default

        assert _extract_setting_default(settings, "DATABASE_URL") is None

    def test_syntax_error_returns_none(self, tmp_path):
        settings = tmp_path / "settings.py"
        settings.write_text("def (:\n", encoding="utf-8")
        from kaira.commands.db_cmd import _extract_setting_default

        assert _extract_setting_default(settings, "DATABASE_URL") is None


# ---------------------------------------------------------------------------
# FEATURE A — env audit / prune
# ---------------------------------------------------------------------------


class TestEnvAuditPrune:
    def _seed_env(self, project):
        _write_config(project)
        (project / ".env.development").write_text(
            "APP_ENV=development\n"
            "DATABASE_URL=sqlite:///./app.db\n"
            "REDIS_URL=redis://localhost:6379\n",
            encoding="utf-8",
        )
        (project / ".env.production").write_text(
            "APP_ENV=production\n"
            "DATABASE_URL=sqlite:///./app.db\n"
            "REDIS_URL=redis://localhost:6379\n",
            encoding="utf-8",
        )

    def test_audit_flags_unused_cache_key(self, project):
        self._seed_env(project)
        result = runner.invoke(app, ["env", "audit"])
        assert result.exit_code == 0
        assert "REDIS_URL" in result.output
        assert "Unused" in result.output

    def test_prune_removes_unused_keeps_core(self, project):
        self._seed_env(project)
        result = runner.invoke(app, ["env", "prune", "--force"])
        assert result.exit_code == 0
        dev = (project / ".env.development").read_text()
        assert "REDIS_URL" not in dev
        assert "DATABASE_URL" in dev  # core key preserved

    def test_prune_blocked_in_production(self, project, monkeypatch):
        self._seed_env(project)
        monkeypatch.setenv("APP_ENV", "production")
        result = runner.invoke(app, ["env", "prune", "--force"])
        assert result.exit_code == 1

    def test_referenced_key_not_pruned(self, project):
        self._seed_env(project)
        # Reference REDIS_URL in code → it must be kept even though cache is off.
        (project / "app.py").write_text(
            "import os\nx = os.environ['REDIS_URL']\n", encoding="utf-8"
        )
        runner.invoke(app, ["env", "prune", "--force"])
        assert "REDIS_URL" in (project / ".env.development").read_text()


# ---------------------------------------------------------------------------
# kaira sync model
# ---------------------------------------------------------------------------


class TestSyncModel:
    def _generate_user(self, project, fields="name:str"):
        _write_config(project)
        result = runner.invoke(
            app, ["generate", "model", "User", "--fields", fields, "--force"]
        )
        assert result.exit_code == 0

    def test_dry_run_changes_nothing(self, project):
        self._generate_user(project)
        before = (project / "schemas" / "user_schema.py").read_text()
        result = runner.invoke(
            app, ["sync", "model", "User", "--fields", "phone:str", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "+ phone" in result.output
        after = (project / "schemas" / "user_schema.py").read_text()
        assert before == after  # untouched

    def test_inline_field_cascades_to_schema(self, project):
        self._generate_user(project)
        result = runner.invoke(
            app, ["sync", "model", "User", "--fields", "phone:str", "--force"]
        )
        assert result.exit_code == 0
        assert "phone" in (project / "models" / "user.py").read_text()
        assert "phone" in (project / "schemas" / "user_schema.py").read_text()

    def test_snapshot_updated(self, project):
        self._generate_user(project)
        runner.invoke(
            app, ["sync", "model", "User", "--fields", "phone:str", "--force"]
        )
        snap = json.loads((project / ".kaira.json").read_text())
        names = [f["name"] for f in snap["generated_models"][0]["fields"]]
        assert "phone" in names

    def test_service_flagged_not_rewritten(self, project):
        self._generate_user(project)
        service_before = (project / "services" / "user_service.py").read_text()
        result = runner.invoke(
            app, ["sync", "model", "User", "--fields", "phone:str", "--force"]
        )
        assert "may need handling" in result.output
        service_after = (project / "services" / "user_service.py").read_text()
        assert service_before == service_after  # never auto-rewritten

    def test_hand_edited_model_detected_via_ast(self, project):
        self._generate_user(project)
        model_path = project / "models" / "user.py"
        txt = model_path.read_text().replace(
            "    uuid: Mapped[str]",
            "    age: Mapped[int] = mapped_column(Integer, nullable=False)\n    uuid: Mapped[str]",
            1,
        )
        model_path.write_text(txt)
        result = runner.invoke(app, ["sync", "model", "User", "--force"])
        assert result.exit_code == 0
        assert "+ age" in result.output
        assert "age" in (project / "schemas" / "user_schema.py").read_text()

    def test_unknown_model_errors(self, project):
        _write_config(project)
        result = runner.invoke(app, ["sync", "model", "Ghost"])
        assert result.exit_code == 1

    def test_sync_all(self, project):
        self._generate_user(project)
        runner.invoke(
            app, ["generate", "model", "Post", "--fields", "title:str", "--force"]
        )
        result = runner.invoke(app, ["sync", "model", "--all", "--dry-run"])
        assert result.exit_code == 0
        assert "User" in result.output
        assert "Post" in result.output
