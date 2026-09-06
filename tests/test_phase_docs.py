"""Tests for Documentation Generation Phase (docs generate, docs status, docs_render)."""

import json
from pathlib import Path
from typer.testing import CliRunner

from kaira.main import app
from kaira.core.docs_render import (
    DOC_CONFIG,
    DOC_ENDPOINTS,
    DOC_ERD,
    DOC_MODELS,
    DOC_README,
    is_docs_out_of_sync,
    maybe_autodocs,
    render_configuration_doc,
    render_endpoints_doc,
    render_erd_doc,
    render_models_doc,
    render_readme_doc,
)
from kaira.config import get_config

runner = CliRunner()


def _setup_project(tmp_path: Path, db_type: str = "sqlite") -> None:
    """Helper to set up a project with multiple models, relations, routes, and config."""
    config_data = {
        "output_dir": ".",
        "models_dir": "models",
        "repositories_dir": "repositories",
        "schemas_dir": "schemas",
        "services_dir": "services",
        "routers_dir": "routers",
        "db_type": db_type,
        "api_version": "v1",
        "auth_type": "jwt",
        "cache_enabled": True,
        "generated_models": [
            {
                "name": "User",
                "fields": [
                    {"name": "email", "type": "str"},
                    {"name": "password", "type": "str"},
                    {"name": "age", "type": "Optional[int]"},
                ],
                "relations": [{"type": "one-to-many", "target": "Order"}],
            },
            {
                "name": "Order",
                "fields": [
                    {"name": "total_amount", "type": "float"},
                    {"name": "status", "type": "str"},
                ],
                "relations": [{"type": "many-to-one", "target": "User"}],
            },
        ],
    }
    (tmp_path / ".kaira.json").write_text(
        json.dumps(config_data, indent=2), encoding="utf-8"
    )

    # Create dummy router files for route discovery
    routers_dir = tmp_path / "routers"
    routers_dir.mkdir(parents=True, exist_ok=True)
    (routers_dir / "__init__.py").touch()

    user_router_code = """
from fastapi import APIRouter, Depends
from auth.dependencies import get_current_user

router = APIRouter(prefix="/users", tags=["User"])

@router.get("/", summary="List users")
def list_users(current_user: dict = Depends(get_current_user)):
    return []

@router.get("/{id}", summary="Get user by ID")
def get_user(id: str, current_user: dict = Depends(get_current_user)):
    return {}

@router.post("/", summary="Create user")
def create_user():
    return {}
"""
    (routers_dir / "user_router.py").write_text(user_router_code, encoding="utf-8")

    # Auth router
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "__init__.py").touch()
    auth_dep_code = """
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    return {"id": "1"}
"""
    (auth_dir / "dependencies.py").write_text(auth_dep_code, encoding="utf-8")

    auth_router_code = """
from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", summary="Login")
def login():
    return {"token": "xyz"}
"""
    (auth_dir / "router.py").write_text(auth_router_code, encoding="utf-8")

    # Main app
    main_code = """
from fastapi import FastAPI
from routers.user_router import router as user_router
from auth.router import router as auth_router

app = FastAPI()
app.include_router(user_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")

@app.get("/health", tags=["HealthCheck"])
def health():
    return {"status": "ok"}
"""
    (tmp_path / "main.py").write_text(main_code, encoding="utf-8")

    # Core cache
    core_dir = tmp_path / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "cache.py").write_text("# Redis cache\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Document Content Tests
# ---------------------------------------------------------------------------


def test_render_models_doc(tmp_path, monkeypatch):
    """Test models.md includes field tables, constraints, types, nullability, and relations."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    config = get_config()

    doc = render_models_doc(config, tmp_path)
    assert "# Model Reference" in doc
    assert "## User" in doc
    assert "## Order" in doc
    assert "| `email` | `str` | max_length=255, pattern=email | No | — |" in doc
    assert "| `age` | `int` | — | Yes | — |" in doc
    assert "- → has many [Order](#order)" in doc
    assert "- → belongs to [User](#user)" in doc


def test_render_models_doc_single_model_update(tmp_path, monkeypatch):
    """Test surgical single model update preserving other model sections."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    config = get_config()

    initial_doc = render_models_doc(config, tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "models.md").write_text(initial_doc, encoding="utf-8")

    # Update User in config
    config.generated_models[0]["fields"].append({"name": "phone", "type": "str"})
    (tmp_path / ".kaira.json").write_text(
        json.dumps(config.to_dict()), encoding="utf-8"
    )

    updated_doc = render_models_doc(
        config, tmp_path, target_model="User", existing_content=initial_doc
    )
    assert "## User" in updated_doc
    assert "| `phone` | `str` | max_length=20, pattern=E.164 | No | — |" in updated_doc
    # Order section must be preserved!
    assert "## Order" in updated_doc
    assert "| `total_amount` | `float` |" in updated_doc


def test_render_endpoints_doc(tmp_path, monkeypatch):
    """Test endpoints.md groups by resource and includes auth/cache/rate-limit columns."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    config = get_config()

    doc = render_endpoints_doc(config, tmp_path)
    assert "# Endpoint Reference" in doc
    assert "## User" in doc or "## Users" in doc or "## Auth" in doc
    assert "| Route | Method | Auth | Cached | Rate limit |" in doc
    assert "🔒 Required" in doc
    assert "kaira api export" in doc
    assert "kaira api postman" in doc


def test_render_erd_doc_relational(tmp_path, monkeypatch):
    """Test erd.md produces valid Mermaid block with cardinality."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path, db_type="postgresql")
    config = get_config()

    doc = render_erd_doc(config, tmp_path)
    assert "# Entity Relationship Diagram" in doc
    assert "```mermaid" in doc
    assert "erDiagram" in doc
    assert "User {" in doc
    assert "Order {" in doc
    assert 'User ||--o{ Order : "has many"' in doc


def test_render_erd_doc_nosql(tmp_path, monkeypatch):
    """Test erd.md handles MongoDB / Atlas / Firestore logical relationships."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path, db_type="mongodb")
    config = get_config()

    doc = render_erd_doc(config, tmp_path)
    assert "Document relationships (logical)" in doc
    assert 'User .. Order : "references"' in doc


def test_render_configuration_doc_security(tmp_path, monkeypatch):
    """Test configuration.md documents keys and placeholders, never reading live .env values."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # Put fake secret in .env.development and .env.production
    fake_secret = "LEAKED_SUPER_SECRET_VALUE_999"
    (tmp_path / ".env.development").write_text(
        f"JWT_SECRET_KEY={fake_secret}\nDATABASE_URL=postgres://user:pass@host/db\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.production").write_text(
        f"JWT_SECRET_KEY={fake_secret}\n", encoding="utf-8"
    )

    config = get_config()
    doc = render_configuration_doc(config, tmp_path)

    assert "# Configuration Reference" in doc
    assert "## Feature Flags" in doc
    assert "## Environment Variables" in doc
    assert "DATABASE_URL" in doc
    assert "JWT_SECRET_KEY" in doc
    # Assert secret never appears!
    assert fake_secret not in doc
    assert "pass@host" not in doc


def test_render_readme_doc(tmp_path, monkeypatch):
    """Test README.md index links the 4 docs, includes Purpose & Overview, and mentions API export commands."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    config = get_config()

    doc = render_readme_doc(config, tmp_path)
    assert "Project Documentation" in doc
    assert "## Purpose" in doc
    assert "## Overview" in doc
    assert "System Architecture" in doc
    assert "Technical Stack & Configuration" in doc
    assert "[Model Reference](models.md)" in doc
    assert "[Endpoint Reference](endpoints.md)" in doc
    assert "[Entity Relationship Diagram](erd.md)" in doc
    assert "[Configuration Reference](configuration.md)" in doc
    assert "kaira api export" in doc
    assert "kaira api postman" in doc


def test_render_root_readme_doc(tmp_path, monkeypatch):
    """Test project root README.md includes Overview, Purpose, Architecture, Models table, Quickstart."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)
    config = get_config()

    from kaira.core.docs_render import render_root_readme_doc

    doc = render_root_readme_doc(config, tmp_path)
    assert "Overview & Purpose" in doc
    assert "Architecture & Directory Structure" in doc
    assert "Registered Domain Models" in doc
    assert "**`User`**" in doc
    assert "**`Order`**" in doc
    assert "Quick Start" in doc
    assert "Project Documentation" in doc
    assert "Kaira CLI Management Commands" in doc


# ---------------------------------------------------------------------------
# CLI Command Tests: kaira docs generate & kaira docs status
# ---------------------------------------------------------------------------


def test_docs_generate_all(tmp_path, monkeypatch):
    """Test `kaira docs generate` generates all documentation files including root README.md."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    result = runner.invoke(app, ["docs", "generate"])
    assert result.exit_code == 0
    assert (tmp_path / "README.md").is_file()
    assert (tmp_path / "docs" / DOC_README).is_file()
    assert (tmp_path / "docs" / DOC_MODELS).is_file()
    assert (tmp_path / "docs" / DOC_ENDPOINTS).is_file()
    assert (tmp_path / "docs" / DOC_ERD).is_file()
    assert (tmp_path / "docs" / DOC_CONFIG).is_file()


def test_docs_generate_only_readme(tmp_path, monkeypatch):
    """Test `kaira docs generate --only readme` generates both root and docs READMEs."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    result = runner.invoke(app, ["docs", "generate", "--only", "readme"])
    assert result.exit_code == 0
    assert (tmp_path / "README.md").is_file()
    assert (tmp_path / "docs" / DOC_README).is_file()
    assert not (tmp_path / "docs" / DOC_MODELS).exists()


def test_docs_generate_up_to_date_detection(tmp_path, monkeypatch):
    """Test up-to-date detection suppresses prompts and redundant writes."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # First run generates
    r1 = runner.invoke(app, ["docs", "generate"])
    assert r1.exit_code == 0

    # Second run detects up to date
    r2 = runner.invoke(app, ["docs", "generate"])
    assert r2.exit_code == 0
    assert "Documentation is up to date" in r2.output


def test_docs_generate_dry_run(tmp_path, monkeypatch):
    """Test `--dry-run` shows plan and writes no files."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    result = runner.invoke(app, ["docs", "generate", "--dry-run"])
    assert result.exit_code == 0
    assert "Documentation Plan" in result.output or "Docs Plan" in result.output
    assert not (tmp_path / "docs").exists()


def test_docs_generate_only_flag(tmp_path, monkeypatch):
    """Test `--only` generates only the specified document."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    result = runner.invoke(app, ["docs", "generate", "--only", "erd"])
    assert result.exit_code == 0
    assert (tmp_path / "docs" / DOC_ERD).is_file()
    assert not (tmp_path / "docs" / DOC_MODELS).exists()
    assert not (tmp_path / "docs" / DOC_ENDPOINTS).exists()


def test_docs_generate_custom_output_dir(tmp_path, monkeypatch):
    """Test `--output` generates into a custom directory."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    out_dir = tmp_path / "custom_docs"
    result = runner.invoke(app, ["docs", "generate", "--output", str(out_dir)])
    assert result.exit_code == 0
    assert (out_dir / DOC_MODELS).is_file()
    assert (out_dir / DOC_README).is_file()


def test_docs_generate_single_model_cli(tmp_path, monkeypatch):
    """Test `kaira docs generate User` updates only models.md for User."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # Initial generate
    runner.invoke(app, ["docs", "generate"])

    # Update User
    result = runner.invoke(app, ["docs", "generate", "User", "--quiet"])
    assert result.exit_code == 0
    assert (tmp_path / "docs" / DOC_MODELS).is_file()


def test_docs_status_command(tmp_path, monkeypatch):
    """Test `kaira docs status` reports document freshness table."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # Before generation - should report missing
    r1 = runner.invoke(app, ["docs", "status"])
    assert r1.exit_code == 0
    assert "Missing" in r1.output

    # Generate docs
    runner.invoke(app, ["docs", "generate", "--quiet"])

    # After generation - should report up to date
    r2 = runner.invoke(app, ["docs", "status"])
    assert r2.exit_code == 0
    assert "Up to date" in r2.output


def test_maybe_autodocs_hook(tmp_path, monkeypatch):
    """Test maybe_autodocs detects out-of-sync docs and prompts."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # Generate initial docs
    runner.invoke(app, ["docs", "generate", "--quiet"])
    assert not is_docs_out_of_sync(tmp_path)

    # Alter project state (add new model to config)
    config = get_config()
    config.generated_models.append(
        {
            "name": "Product",
            "fields": [{"name": "price", "type": "float"}],
            "relations": [],
        }
    )
    (tmp_path / ".kaira.json").write_text(
        json.dumps(config.to_dict()), encoding="utf-8"
    )

    assert is_docs_out_of_sync(tmp_path)

    # Test auto-prompt in quiet mode (no prompt, returns False)
    assert not maybe_autodocs(quiet=True, root=tmp_path)

    # In interactive mode with 'y'
    monkeypatch.setattr("kaira.core.docs_render.is_interactive", lambda: True)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *args, **kwargs: "y")
    assert maybe_autodocs(quiet=False, root=tmp_path)

    # After auto-regeneration, docs should be up to date
    assert not is_docs_out_of_sync(tmp_path)


def test_secret_leakage_regression(tmp_path, monkeypatch):
    """Regression test: assert no value from any .env.* reaches any generated documentation file."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    secret_key = "TOP_SECRET_JWT_KEY_ABCD_1234567890"
    secret_db = (
        "postgresql://secret_user:super_secret_password@db.secret.com:5432/secretdb"
    )
    secret_api = "pk_live_secret_stripe_live_key_99999"

    for env_name in ("development", "staging", "production"):
        (tmp_path / f".env.{env_name}").write_text(
            f"JWT_SECRET_KEY={secret_key}\n"
            f"DATABASE_URL={secret_db}\n"
            f"STRIPE_API_KEY={secret_api}\n",
            encoding="utf-8",
        )

    result = runner.invoke(app, ["docs", "generate", "--quiet"])
    assert result.exit_code == 0

    # Scan all generated files in docs/
    for doc_file in (tmp_path / "docs").glob("*.md"):
        content = doc_file.read_text(encoding="utf-8")
        assert secret_key not in content, f"Secret leaked in {doc_file.name}"
        assert "super_secret_password" not in content, (
            f"Password leaked in {doc_file.name}"
        )
        assert secret_api not in content, f"API key leaked in {doc_file.name}"


def test_api_list_and_env_audit_invariance(tmp_path, monkeypatch):
    """Test api list and env audit commands execute cleanly after data function extraction."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # Test api list
    from kaira.commands.api_cmd import collect_api_routes

    spec = {
        "paths": {
            "/users": {
                "get": {"summary": "List users"},
                "post": {"summary": "Create user"},
            }
        }
    }
    routes = collect_api_routes(spec)
    assert len(routes) == 2
    assert routes[0]["method"] == "GET"
    assert routes[0]["path"] == "/users"

    # Test env audit
    from kaira.commands.env_cmd import collect_env_audit_rows

    config = get_config()
    (tmp_path / ".env.development").write_text(
        "APP_ENV=development\nAPP_NAME=test\n", encoding="utf-8"
    )
    rows = collect_env_audit_rows(config, tmp_path)
    assert len(rows) > 0


def test_guide_docs_command():
    """Test `kaira guide docs` output."""
    result = runner.invoke(app, ["guide", "docs"])
    assert result.exit_code == 0
    assert "kaira docs generate" in result.output
    assert "kaira docs status" in result.output


def test_fallback_models_snapshot_from_files(tmp_path, monkeypatch):
    """Test deriving model field snapshot from model files when .kaira.json has empty list."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps({"db_type": "sqlite", "generated_models": []}), encoding="utf-8"
    )
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "__init__.py").touch()
    (models_dir / "customer.py").write_text(
        """
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer

class Customer:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(255))
    loyalty_points: Mapped[int] = mapped_column(Integer)
""",
        encoding="utf-8",
    )

    config = get_config()
    doc = render_models_doc(config, tmp_path)
    assert "## Customer" in doc
    assert "| `full_name` | `str` |" in doc


def test_erd_truncation_with_many_fields(tmp_path, monkeypatch):
    """Test ERD entity block truncates fields when model has > 8 fields."""
    monkeypatch.chdir(tmp_path)
    many_fields = [{"name": f"field_{i}", "type": "str"} for i in range(12)]
    config_data = {
        "db_type": "sqlite",
        "generated_models": [
            {
                "name": "BigModel",
                "fields": many_fields,
                "relations": [{"type": "many-to-many", "target": "Tag"}],
            }
        ],
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(config_data), encoding="utf-8")
    config = get_config()
    doc = render_erd_doc(config, tmp_path)
    assert "... 4 more fields" in doc
    assert 'BigModel }o--o{ Tag : "relates to"' in doc


def test_empty_project_docs(tmp_path, monkeypatch):
    """Test docs generation on an empty project with no models and no routes."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps({"generated_models": []}), encoding="utf-8"
    )
    config = get_config()

    doc_models = render_models_doc(config, tmp_path)
    assert "No models registered" in doc_models

    doc_erd = render_erd_doc(config, tmp_path)
    assert "EMPTY_PROJECT" in doc_erd

    doc_ep = render_endpoints_doc(config, tmp_path)
    assert "No endpoints discovered" in doc_ep


def test_docs_generate_only_config_and_models(tmp_path, monkeypatch):
    """Test --only config and --only models flags."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    r1 = runner.invoke(app, ["docs", "generate", "--only", "config"])
    assert r1.exit_code == 0
    assert (tmp_path / "docs" / DOC_CONFIG).is_file()
    assert not (tmp_path / "docs" / DOC_MODELS).exists()

    r2 = runner.invoke(app, ["docs", "generate", "--only", "models"])
    assert r2.exit_code == 0
    assert (tmp_path / "docs" / DOC_MODELS).is_file()


def test_interactive_overwrite_choices(tmp_path, monkeypatch):
    """Test interactive overwrite choices: skip and view."""
    monkeypatch.chdir(tmp_path)
    _setup_project(tmp_path)

    # First write
    runner.invoke(app, ["docs", "generate", "--quiet"])

    # Modify file on disk
    (tmp_path / "docs" / DOC_MODELS).write_text("# Old models\n", encoding="utf-8")

    # Simulate user choosing 'v' then 's' (skip)
    choices = iter(["v", "s", "s", "s", "s", "s"])
    monkeypatch.setattr("kaira.core.docs_render.is_interactive", lambda: True)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda *args, **kwargs: next(choices))

    result = runner.invoke(app, ["docs", "generate"])
    assert result.exit_code == 0
    assert (tmp_path / "docs" / DOC_MODELS).read_text(
        encoding="utf-8"
    ) == "# Old models\n"
