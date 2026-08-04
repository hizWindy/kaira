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

    def test_hand_edited_model_with_enums_and_union_types_detected(self, project):
        """Sync must detect hand-edited fields even if Enum classes precede User class or str | None union syntax is used."""
        self._generate_user(project, fields="user_name:str, password:str")
        model_path = project / "models" / "user.py"

        # Prepend an Enum class and add str | None and int fields to User model
        edited_model = (
            "from enum import Enum\n\n"
            "class UserRole(str, Enum):\n"
            "    ADMIN = 'admin'\n"
            "    USER = 'user'\n\n"
            + model_path.read_text().replace(
                "    uuid: Mapped[str]",
                "    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)\n"
                "    age: Mapped[int] = mapped_column(Integer, nullable=False)\n"
                "    uuid: Mapped[str]",
                1,
            )
        )
        model_path.write_text(edited_model)

        result = runner.invoke(app, ["sync", "model", "User"])
        assert result.exit_code == 0

        schema_code = (project / "schemas" / "user_schema.py").read_text()
        assert "user_name" in schema_code
        assert "password" in schema_code
        assert "phone: Optional[str]" in schema_code
        assert "age: int" in schema_code

    def test_sync_detects_legacy_column_syntax_and_qualified_types(self, project):
        """Sync must detect fields defined via legacy Column(...) syntax or qualified typing.Optional annotations."""
        self._generate_user(project, fields="user_name:str")
        model_path = project / "models" / "user.py"

        legacy_code = (
            "import typing\n"
            "from sqlalchemy import Column, String, Integer\n"
            "from core.database import Base\n\n"
            "class User(Base):\n"
            "    user_name = Column(String(255), nullable=False)\n"
            "    phone = Column(String(20), nullable=True)\n"
            "    age = Column(Integer)\n"
            "    notes: typing.Optional[str] = None\n"
        )
        model_path.write_text(legacy_code)

        result = runner.invoke(app, ["sync", "model", "User"])
        assert result.exit_code == 0

        schema_code = (project / "schemas" / "user_schema.py").read_text()
        assert "user_name: str" in schema_code or "user_name:" in schema_code
        assert "phone: Optional[str]" in schema_code
        assert "age: int" in schema_code
        assert "notes: Optional[str]" in schema_code

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

    def test_sync_without_force_applies_cascade(self, project):
        """Task 1: sync without --force must update cascade layers on disk."""
        self._generate_user(project, fields="name:str")
        result = runner.invoke(app, ["sync", "model", "User", "--fields", "phone:str"])
        assert result.exit_code == 0

        model_code = (project / "models" / "user.py").read_text()
        schema_code = (project / "schemas" / "user_schema.py").read_text()
        router_code = (project / "routers" / "user_router.py").read_text()

        assert "phone" in model_code
        assert "phone: str" in schema_code or "phone: str = Field" in schema_code
        assert "phone: Optional[str]" in schema_code
        assert "UserResponse" in router_code

    def test_sync_cascades_existing_seed(self, project):
        """Task 2: sync updates an existing seed script to include added fields."""
        self._generate_user(project, fields="name:str")
        # Generate seed script first
        gen_seed_res = runner.invoke(app, ["seed", "generate", "User"])
        assert gen_seed_res.exit_code == 0
        seed_path = project / "seeds" / "seed_user.py"
        assert seed_path.exists()
        assert "phone" not in seed_path.read_text()

        # Sync model with new field
        sync_res = runner.invoke(
            app, ["sync", "model", "User", "--fields", "phone:str"]
        )
        assert sync_res.exit_code == 0
        assert "phone" in seed_path.read_text()

    def test_sync_does_not_create_missing_seed(self, project):
        """Task 2: sync does NOT create a seed script if none existed before."""
        self._generate_user(project, fields="name:str")
        seed_path = project / "seeds" / "seed_user.py"
        assert not seed_path.exists()

        sync_res = runner.invoke(
            app, ["sync", "model", "User", "--fields", "phone:str"]
        )
        assert sync_res.exit_code == 0
        assert not seed_path.exists()


def test_sql_seed_base_time_timezone_alignment():
    """Task 3: verify SQL seed template and ORM model template timestamp timezone alignment."""
    from kaira.core.generator import TEMPLATES_DIR

    model_tmpl = (TEMPLATES_DIR / "model.py.j2").read_text(encoding="utf-8")
    seed_tmpl = (TEMPLATES_DIR / "seed_model_sql.py.j2").read_text(encoding="utf-8")

    # ORM model emits DateTime(timezone=True)
    assert "DateTime(timezone=True)" in model_tmpl
    # Seed template uses timezone-aware BASE_TIME (timezone.utc)
    assert "BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)" in seed_tmpl


def test_delete_endpoint_response_schema(tmp_path, monkeypatch):
    """Task 4: delete endpoint has response_model=MessageResponse and message_schema.py is created."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    result = runner.invoke(
        app, ["generate", "model", "User", "--fields", "name:str", "--force"]
    )
    assert result.exit_code == 0

    message_schema_path = tmp_path / "schemas" / "message_schema.py"
    assert message_schema_path.exists()
    assert "class MessageResponse(BaseModel):" in message_schema_path.read_text()

    router_path = tmp_path / "routers" / "user_router.py"
    router_code = router_path.read_text()
    assert "from schemas.message_schema import MessageResponse" in router_code
    assert "response_model=MessageResponse" in router_code
    assert "-> MessageResponse:" in router_code


def test_create_schema_excludes_server_managed_fields(tmp_path, monkeypatch):
    """Task 5: Create and Base schemas exclude server-managed fields like uuid, created_at, updated_at."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    result = runner.invoke(
        app,
        [
            "generate",
            "model",
            "Item",
            "--fields",
            "title:str, uuid:str, created_at:datetime",
            "--force",
        ],
    )
    assert result.exit_code == 0

    schema_code = (tmp_path / "schemas" / "item_schema.py").read_text()

    # Extract class definitions
    base_idx = schema_code.find("class ItemBase")
    create_idx = schema_code.find("class ItemCreate")
    update_idx = schema_code.find("class ItemUpdate")
    response_idx = schema_code.find("class ItemResponse")

    base_code = schema_code[base_idx:create_idx]
    create_code = schema_code[create_idx:update_idx]
    response_code = schema_code[response_idx:]

    # ItemBase / ItemCreate must only contain title, NOT uuid or created_at
    assert "title: str" in base_code or "title:" in base_code
    assert "uuid:" not in base_code
    assert "created_at:" not in base_code

    assert "title: str" in create_code or "title:" in create_code
    assert "uuid:" not in create_code

    # ItemResponse must contain uuid, created_at, updated_at explicitly once
    assert "uuid: str" in response_code
    assert "created_at: datetime" in response_code
    assert "updated_at: datetime" in response_code


def test_openapi_generation_succeeds_without_pydantic_user_error(tmp_path, monkeypatch):
    """Verify FastAPI can build openapi.json without PydanticUserError on UserUpdate / schemas."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    result = runner.invoke(
        app,
        [
            "generate",
            "model",
            "User",
            "--fields",
            "username:str, email:str, phone:Optional[str]",
            "--force",
        ],
    )
    assert result.exit_code == 0

    import importlib
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        schema_mod = importlib.import_module("schemas.user_schema")
        # This module uses `from __future__ import annotations`, so the endpoint
        # annotation below is a *string* that FastAPI resolves against this
        # module's globals. A dotted `schema_mod.UserUpdate` would resolve
        # against a function local and always fail as an unresolvable
        # ForwardRef — masking whether the generated schema is actually valid.
        # Publishing the bare name here is what makes the annotation resolvable.
        globals()["UserUpdate"] = schema_mod.UserUpdate

        from fastapi import FastAPI

        fastapi_app = FastAPI()

        @fastapi_app.put("/users/{uuid}")
        def update_user(data: UserUpdate):
            return data

        openapi_schema = fastapi_app.openapi()
        assert "paths" in openapi_schema
        assert "/users/{uuid}" in openapi_schema["paths"]

        # The model must be fully defined, not a pydantic mock. A schema whose
        # `Optional` never resolved still yields a path entry but no usable
        # body definition — that is the shape of the /docs failure.
        assert "UserUpdate" in openapi_schema["components"]["schemas"]
        body_props = openapi_schema["components"]["schemas"]["UserUpdate"]["properties"]
        assert {"username", "email", "phone"} <= set(body_props)
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        globals().pop("UserUpdate", None)
        sys.modules.pop("schemas.user_schema", None)
