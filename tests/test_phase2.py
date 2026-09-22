"""CLI integration tests for Phase 2 security and scaffolding commands."""

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


class TestPhase2Commands:
    def test_health_command(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("health")
            assert result.exit_code == 0
            assert "Kaira Health Check" in result.output
            assert "Security Score" in result.output

    def test_auth_generate_jwt(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("auth", "generate", "--type", "jwt", "--force")
            assert result.exit_code == 0
            assert "boileplate" in result.output or "complete" in result.output
            assert (cwd / "auth" / "dependencies.py").exists()
            assert (cwd / "auth" / "router.py").exists()
            assert (cwd / "auth" / "service.py").exists()
            assert (cwd / "auth" / "schemas.py").exists()
            assert (cwd / "auth" / "utils.py").exists()
            assert (cwd / "models" / "blacklisted_token.py").exists()
            assert (cwd / "rate_limit.py").exists()

    def test_auth_generate_oauth2(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("auth", "generate", "--type", "oauth2", "--force")
            assert result.exit_code == 0
            assert (cwd / "auth" / "oauth2.py").exists()

    def test_auth_generate_api_key(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("auth", "generate", "--type", "api-key", "--force")
            assert result.exit_code == 0
            assert (cwd / "auth" / "api_key.py").exists()

    def test_env_init_and_validate(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("env", "init", "--force")
            assert result.exit_code == 0
            assert (cwd / "config" / "settings.py").exists()
            assert (cwd / ".env.development").exists()
            assert (cwd / ".env.production").exists()
            assert (cwd / ".env.example").exists()

            # Switch environment
            result_switch = run("env", "switch", "development")
            assert result_switch.exit_code == 0
            assert (cwd / ".env").exists()

            # Validate environment
            result_val = run("env", "validate")
            assert result_val.exit_code == 0
            assert (
                "validation warnings" in result_val.output
                or "checks passed" in result_val.output
            )

    def test_docker_init(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("docker", "init", "--with-compose", "--force")
            assert result.exit_code == 0
            assert (cwd / "Dockerfile").exists()
            assert (cwd / "docker-compose.yml").exists()
            assert (cwd / "docker-compose.prod.yml").exists()
            assert (cwd / ".dockerignore").exists()

    def test_ci_generate(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("ci", "generate", "--platform", "github", "--force")
            assert result.exit_code == 0
            assert (cwd / ".github" / "workflows" / "test.yml").exists()
            assert (cwd / ".github" / "workflows" / "security.yml").exists()
            assert (cwd / ".github" / "workflows" / "deploy.yml").exists()

    def test_websocket_generate(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("websocket", "generate", "Chat", "--force")
            assert result.exit_code == 0
            assert (cwd / "websockets" / "manager.py").exists()
            assert (cwd / "websockets" / "chat_router.py").exists()
            assert (cwd / "websockets" / "chat_schemas.py").exists()

    def test_seed_generate(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            # First generate a model so config has it tracked
            run(
                "generate",
                "model",
                "Product",
                "--fields",
                "name:str,price:float",
                "--force",
            )
            result = run("seed", "generate", "Product", "--force")
            assert result.exit_code == 0
            assert (cwd / "seeds" / "seed_product.py").exists()

    def test_version_create_and_migrate(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            result = run("version", "create", "v1")
            assert result.exit_code == 0
            assert (cwd / "api" / "v1" / "routers").exists()

    def test_audit_commands(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result_routes = run("audit", "routes")
            assert result_routes.exit_code == 0

            result_sec = run("audit", "security")
            assert result_sec.exit_code == 0
            assert "Security Score" in result_sec.output
