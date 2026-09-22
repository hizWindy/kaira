"""CLI integration tests using Typer's test runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from typer.main import get_command

from kaira.main import app

runner = CliRunner()
cli = get_command(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(*args):
    """Invoke the kaira CLI with the given arguments."""
    return runner.invoke(cli, list(args))


# ---------------------------------------------------------------------------
# version / help
# ---------------------------------------------------------------------------


class TestVersionAndHelp:
    def test_version_flag(self):
        result = run("--version")
        assert result.exit_code == 0
        assert "0.2" in result.output

    def test_version_command(self):
        result = run("version")
        assert result.exit_code == 0
        assert "Kaira" in result.output

    def test_help(self):
        result = run("--help")
        assert result.exit_code == 0
        assert "generate" in result.output
        assert "migrate" in result.output
        assert "init" in result.output

    def test_generate_help(self):
        result = run("generate", "--help")
        assert result.exit_code == 0
        assert "model" in result.output


# ---------------------------------------------------------------------------
# kaira generate model
# ---------------------------------------------------------------------------


class TestGenerateModel:
    def test_basic_generation(self, tmp_path):
        """Generate a full pipeline for a User model."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run(
                "generate",
                "model",
                "User",
                "--fields",
                "username:str, email:str, age:int",
            )
        assert result.exit_code == 0
        assert "User" in result.output
        assert "✓" in result.output

    def test_invalid_model_name(self):
        result = run("generate", "model", "user")
        assert result.exit_code != 0
        assert "PascalCase" in result.output

    def test_invalid_field_type(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "model", "User", "--fields", "data:uuid")
        assert result.exit_code != 0
        assert "Unsupported" in result.output

    def test_simple_tier(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run(
                "generate", "model", "User", "--fields", "name:str", "--tier", "simple"
            )
        assert result.exit_code == 0
        assert "simple" in result.output

    def test_invalid_tier(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run(
                "generate", "model", "User", "--fields", "name:str", "--tier", "invalid"
            )
        assert result.exit_code != 0

    def test_files_created(self, tmp_path):
        """Verify that all 5 layer files are actually written."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            run(
                "generate",
                "model",
                "Product",
                "--fields",
                "name:str, price:float",
                "--force",
            )
            assert (cwd / "models" / "product.py").exists()
            assert (cwd / "schemas" / "product_schema.py").exists()
            assert (cwd / "services" / "product_service.py").exists()
            assert (cwd / "repositories" / "product_repository.py").exists()
            assert (cwd / "routers" / "product_router.py").exists()

    def test_kaira_json_created(self, tmp_path):
        """Verify .kaira.json is written with the model entry."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            run("generate", "model", "Item", "--fields", "name:str")
            config_file = cwd / ".kaira.json"
            assert config_file.exists()
            data = json.loads(config_file.read_text())
            names = [m["name"] for m in data["generated_models"]]
            assert "Item" in names


# ---------------------------------------------------------------------------
# kaira generate (single layer)
# ---------------------------------------------------------------------------


class TestGenerateSingleLayer:
    def test_generate_router(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "router", "User", "--fields", "name:str")
        assert result.exit_code == 0

    def test_generate_schema(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "schema", "User", "--fields", "name:str")
        assert result.exit_code == 0

    def test_generate_service(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "service", "User", "--fields", "name:str")
        assert result.exit_code == 0

    def test_generate_repository(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "repository", "User", "--fields", "name:str")
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# kaira generate bulk
# ---------------------------------------------------------------------------


class TestGenerateBulk:
    def test_bulk_from_json(self, tmp_path):
        bulk_data = [
            {"name": "User", "fields": {"username": "str", "email": "str"}},
            {"name": "Post", "fields": {"title": "str", "body": "str"}},
        ]
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            json_file = cwd / "models.json"
            json_file.write_text(json.dumps(bulk_data))
            result = run("generate", "bulk", str(json_file), "--force")
        assert result.exit_code == 0
        assert "Bulk generation complete" in result.output

    def test_bulk_missing_file(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "bulk", "nonexistent.json")
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_bulk_invalid_json(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            bad_json = cwd / "bad.json"
            bad_json.write_text("{not: valid json")
            result = run("generate", "bulk", str(bad_json))
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# kaira config
# ---------------------------------------------------------------------------


class TestConfigCommands:
    def test_config_show(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("config", "show")
        assert result.exit_code == 0
        assert "default_tier" in result.output

    def test_config_set_and_get(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            run("config", "set", "default_tier", "simple")
            result = run("config", "get", "default_tier")
        assert result.exit_code == 0
        assert "simple" in result.output

    def test_config_set_invalid_key(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("config", "set", "nonexistent_key", "value")
        assert result.exit_code != 0
        assert "Unknown" in result.output


# ---------------------------------------------------------------------------
# kaira info
# ---------------------------------------------------------------------------


class TestInfoCommand:
    def test_info_no_models(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("info")
        assert result.exit_code == 0

    def test_info_with_models(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            run("generate", "model", "User", "--fields", "name:str")
            result = run("info")
        assert result.exit_code == 0
        assert "User" in result.output


# ---------------------------------------------------------------------------
# kaira check
# ---------------------------------------------------------------------------


class TestCheckCommand:
    def test_check_no_models(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("check")
        assert result.exit_code == 0

    def test_check_with_generated_models(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            run("generate", "model", "User", "--fields", "name:str", "--force")
            result = run("check")
        assert result.exit_code == 0
        assert "User" in result.output


# ---------------------------------------------------------------------------
# kaira list
# ---------------------------------------------------------------------------


class TestListCommands:
    def test_list_models_empty_dir(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("list", "models")
        # Should not crash even if dir doesn't exist
        assert result.exit_code == 0

    def test_list_routes_empty_dir(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("list", "routes")
        assert result.exit_code == 0

    def test_list_models_after_generate(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            run("generate", "model", "User", "--fields", "name:str", "--force")
            result = run("list", "models")
        assert result.exit_code == 0
        assert "user.py" in result.output


# ---------------------------------------------------------------------------
# kaira diff
# ---------------------------------------------------------------------------


class TestDiffCommand:
    def test_diff_no_files(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("diff", "User")
        assert result.exit_code == 0
        assert (
            "not found" in result.output.lower() or "Nothing to diff" in result.output
        )

    def test_diff_invalid_model_name(self):
        result = run("diff", "not_pascal")
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# kaira init -> AGENTS.md
# ---------------------------------------------------------------------------


class TestInitProjectAgents:
    def test_init_generates_agents_md(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run(
                "init",
                "test-agent-app",
                "--db",
                "sqlite",
                "--auth",
                "jwt",
                "--no-docker",
                "--ci",
                "none",
                "--yes",
            )
            assert result.exit_code == 0, result.output
            app_dir = Path.cwd() / "test-agent-app"
            agents_file = app_dir / "AGENTS.md"
            assert agents_file.is_file(), "AGENTS.md was not generated in scaffolded project"
            content = agents_file.read_text(encoding="utf-8")
            assert "test-agent-app" in content
            assert "sqlite" in content.lower()
            assert "5-layer" in content.lower() or "5-Layer" in content

            # Verify .agents/skills library
            skills_dir = app_dir / ".agents" / "skills"
            assert skills_dir.is_dir()
            for skill_name in [
                "kaira-scaffold-model",
                "kaira-db-migrations",
                "kaira-sync-layers",
                "kaira-ai-agent",
                "kaira-quality-gate",
            ]:
                skill_file = skills_dir / skill_name / "SKILL.md"
                assert skill_file.is_file(), f"Missing {skill_name}/SKILL.md"
                text = skill_file.read_text(encoding="utf-8")
                assert text.startswith("---"), f"{skill_name} missing YAML frontmatter"
                assert f"name: {skill_name}" in text
                assert "description:" in text

    def test_init_generates_kaira_framework_structure(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run(
                "init",
                "framework-app",
                "--db",
                "sqlite",
                "--auth",
                "jwt",
                "--no-docker",
                "--ci",
                "none",
                "--yes",
            )
            assert result.exit_code == 0, result.output
            app_dir = Path.cwd() / "framework-app"

            # 1. main.py must use KairaApp
            main_file = app_dir / "main.py"
            assert main_file.is_file(), "main.py was not generated"
            main_code = main_file.read_text(encoding="utf-8")
            assert "from kaira.app import KairaApp" in main_code
            assert "app = KairaApp(" in main_code

            # 2. requirements.txt must contain khaira
            req_file = app_dir / "requirements.txt"
            assert req_file.is_file(), "requirements.txt was not generated"
            req_text = req_file.read_text(encoding="utf-8")
            assert "khaira>=" in req_text

            # 3. pyproject.toml must contain khaira
            pyproject_file = app_dir / "pyproject.toml"
            assert pyproject_file.is_file(), "pyproject.toml was not generated"
            pyproject_text = pyproject_file.read_text(encoding="utf-8")
            assert "khaira>=" in pyproject_text

            # 4. routers/health_router.py must exist
            health_router = app_dir / "routers" / "health_router.py"
            assert health_router.is_file(), "routers/health_router.py was not generated"
            health_code = health_router.read_text(encoding="utf-8")
            assert "router = APIRouter(" in health_code

