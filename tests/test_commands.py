"""CLI integration tests using Typer's test runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devflow.main import app

runner = CliRunner(mix_stderr=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(*args):
    """Invoke the devflow CLI with the given arguments."""
    return runner.invoke(app, list(args))


# ---------------------------------------------------------------------------
# version / help
# ---------------------------------------------------------------------------

class TestVersionAndHelp:
    def test_version_flag(self):
        result = run("--version")
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_version_command(self):
        result = run("version")
        assert result.exit_code == 0
        assert "DevFlow" in result.output

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
# devflow generate model
# ---------------------------------------------------------------------------

class TestGenerateModel:
    def test_basic_generation(self, tmp_path):
        """Generate a full pipeline for a User model."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "model", "User", "--fields", "username:str, email:str, age:int")
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
            result = run("generate", "model", "User", "--fields", "name:str", "--tier", "simple")
        assert result.exit_code == 0
        assert "simple" in result.output

    def test_invalid_tier(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("generate", "model", "User", "--fields", "name:str", "--tier", "invalid")
        assert result.exit_code != 0

    def test_files_created(self, tmp_path):
        """Verify that all 5 layer files are actually written."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            run("generate", "model", "Product", "--fields", "name:str, price:float", "--force")
            assert (cwd / "models" / "product.py").exists()
            assert (cwd / "schemas" / "product_schema.py").exists()
            assert (cwd / "services" / "product_service.py").exists()
            assert (cwd / "repositories" / "product_repository.py").exists()
            assert (cwd / "routers" / "product_router.py").exists()

    def test_devflow_json_created(self, tmp_path):
        """Verify .devflow.json is written with the model entry."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            run("generate", "model", "Item", "--fields", "name:str")
            config_file = cwd / ".devflow.json"
            assert config_file.exists()
            data = json.loads(config_file.read_text())
            names = [m["name"] for m in data["generated_models"]]
            assert "Item" in names


# ---------------------------------------------------------------------------
# devflow generate (single layer)
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
# devflow generate bulk
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
# devflow config
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
# devflow info
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
# devflow check
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
# devflow list
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
# devflow diff
# ---------------------------------------------------------------------------

class TestDiffCommand:
    def test_diff_no_files(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("diff", "User")
        assert result.exit_code == 0
        assert "not found" in result.output.lower() or "Nothing to diff" in result.output

    def test_diff_invalid_model_name(self):
        result = run("diff", "not_pascal")
        assert result.exit_code != 0
