"""CLI integration tests for Phase 3 features (named init, guides, and versioning config)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from typer.main import get_command

from kaira.main import app

runner = CliRunner()
cli = get_command(app)


def run(*args):
    """Invoke the kaira CLI with the given arguments."""
    return runner.invoke(cli, list(args))


class TestPhase3Commands:
    def test_guide_index(self):
        result = run("guide")
        assert result.exit_code == 0
        assert "Available guides:" in result.output
        assert "kaira guide init" in result.output

    def test_guide_subcommands(self):
        sub_guides = [
            "init",
            "generate",
            "auth",
            "migrate",
            "security",
            "test",
            "docker",
            "ci",
            "env",
            "db",
            "config",
        ]
        for topic in sub_guides:
            result = run("guide", topic)
            assert result.exit_code == 0
            assert "Guide:" in result.output or "index" in result.output.lower()
            assert "Tip:" in result.output

    def test_config_set_case_insensitive(self, tmp_path):
        # Create a mock .kaira.json inside isolated env first by doing config set
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("config", "set", "API_VERSION", "v3")
            assert result.exit_code == 0
            assert "api_version = v3" in result.output

            result_get = run("config", "get", "api_version")
            assert result_get.exit_code == 0
            assert "api_version = v3" in result_get.output

    def test_named_init_and_db_awareness(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            # Run init with name argument and sqlite DB
            result = run(
                "init",
                "coolproject",
                "--db",
                "sqlite",
                "--auth",
                "jwt",
                "--no-docker",
                "--ci",
                "none",
            )
            assert result.exit_code == 0
            assert "coolproject" in result.output

            project_dir = cwd / "coolproject"
            assert project_dir.exists()
            assert (project_dir / "models").exists()
            assert (project_dir / "core" / "database.py").exists()
            assert (project_dir / "core" / "logger.py").exists()
            # middleware/security.py and rate_limit.py are no longer scaffolded — KairaApp provides them natively
            assert not (project_dir / "middleware" / "security.py").exists()
            assert not (project_dir / "rate_limit.py").exists()
            assert (project_dir / "pyproject.toml").exists()
            assert (project_dir / ".kaira.json").exists()

            # Verify that settings.py matches sqlite setup
            db_content = (project_dir / "core" / "database.py").read_text()
            assert "create_async_engine" in db_content
            assert "AsyncSession" in db_content

    def test_named_init_mongodb(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            # Run init with name argument and mongodb DB
            result = run(
                "init",
                "mongoproject",
                "--db",
                "mongodb",
                "--auth",
                "none",
                "--no-docker",
                "--ci",
                "none",
            )
            assert result.exit_code == 0

            project_dir = cwd / "mongoproject"
            assert project_dir.exists()

            # Verify database.py matches Beanie MongoDB setup
            db_content = (project_dir / "core" / "database.py").read_text()
            assert "init_beanie" in db_content
            assert "AsyncIOMotorClient" in db_content
