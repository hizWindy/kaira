"""Tests for the dynamic Docker surface: state registry, templates, and commands.

The Docker templates are only correct relative to project state, so most of
these tests assert the *relationship* — this feature flag produces that service,
this database produces those build deps — rather than pinning exact text.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from typer.main import get_command

from kaira.core import docker_render, docker_state
from kaira.main import app

runner = CliRunner()
cli = get_command(app)


def run(*args):
    """Invoke the kaira CLI with the given arguments."""
    return runner.invoke(cli, list(args))


def make_state(**overrides) -> docker_state.ProjectState:
    """Build a ProjectState with sensible test defaults."""
    base = {
        "project_name": "demo-api",
        "project_slug": "demo_api",
        "db_type": "postgresql",
        "python_version": "3.12.8",
    }
    base.update(overrides)
    return docker_state.ProjectState(**base)


def write_project(root: Path, **config) -> None:
    """Write a minimal .kaira.json into *root*."""
    data = {"output_dir": ".", "db_type": "sqlite"}
    data.update(config)
    (root / ".kaira.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Python version resolution
# ---------------------------------------------------------------------------


class TestPythonVersion:
    @pytest.mark.parametrize("minor", docker_state.SUPPORTED_PYTHON)
    def test_minor_resolves_to_pinned_patch(self, minor):
        resolved = docker_state.resolve_python_version(minor)
        assert resolved.startswith(f"{minor}.")
        assert len(resolved.split(".")) == 3

    def test_default_when_omitted(self):
        expected = docker_state.PYTHON_PATCH[docker_state.DEFAULT_PYTHON]
        assert docker_state.resolve_python_version(None) == expected
        assert docker_state.resolve_python_version("") == expected

    def test_explicit_patch_passes_through(self):
        assert docker_state.resolve_python_version("3.12.11") == "3.12.11"

    @pytest.mark.parametrize("bad", ["3.9", "4.0", "latest", "3", "3.12.x"])
    def test_unsupported_rejected(self, bad):
        with pytest.raises(docker_state.InvalidPythonVersion):
            docker_state.resolve_python_version(bad)


# ---------------------------------------------------------------------------
# System build deps — mapping, not an if/else chain
# ---------------------------------------------------------------------------


class TestSystemBuildDeps:
    @pytest.mark.parametrize(
        "db_type,expected",
        [
            ("postgresql", ["gcc", "libpq-dev"]),
            ("supabase", ["gcc", "libpq-dev"]),
            ("mysql", ["gcc", "default-libmysqlclient-dev", "pkg-config"]),
            ("mongodb", []),
            ("atlas", []),
            ("sqlite", []),
            ("firebase", []),
        ],
    )
    def test_deps_per_database(self, db_type, expected):
        assert docker_state.system_build_deps(db_type) == expected

    def test_unknown_database_needs_nothing(self):
        assert docker_state.system_build_deps("cockroachdb") == []


# ---------------------------------------------------------------------------
# Dockerfile template
# ---------------------------------------------------------------------------


def instructions(dockerfile: str) -> str:
    """Return only the Dockerfile's directives, with comment lines removed.

    The template comments deliberately name the things they warn against
    ("not `adduser --disabled-password`", "why `curl` is not installed"), so a
    naive substring check against the whole file would match the explanation
    instead of the instruction.
    """
    return "\n".join(
        line
        for line in dockerfile.splitlines()
        if not line.lstrip().startswith("#") or line.startswith("# syntax=")
    )


class TestDockerfileTemplate:
    def render(self, **overrides) -> str:
        return docker_render.render_files(make_state(**overrides), with_compose=False)[
            "Dockerfile"
        ]

    def test_base_image_pinned_to_full_patch(self):
        content = self.render()
        assert "ARG PYTHON_VERSION=3.12.8" in content
        assert "python:latest" not in content
        assert "FROM python:${PYTHON_VERSION}-slim" in content

    def test_multi_stage_build(self):
        content = self.render()
        assert content.count("FROM python:${PYTHON_VERSION}-slim") == 2
        assert "AS builder" in content

    def test_user_install_copied_from_builder(self):
        content = self.render()
        assert "pip install --no-cache-dir --user -r requirements.txt" in content
        assert "COPY --from=builder --chown=app:app /root/.local" in content
        assert "site-packages" not in instructions(content)

    def test_apt_hardening_and_same_layer_cleanup(self):
        content = self.render(db_type="postgresql")
        assert "--no-install-recommends" in content
        assert "rm -rf /var/lib/apt/lists/*" in content
        # Cleanup must be chained into the same RUN, not a later layer.
        apt_block = content.split("RUN apt-get update")[1].split("\n\n")[0]
        assert "rm -rf /var/lib/apt/lists/*" in apt_block

    def test_no_apt_layer_when_no_deps_needed(self):
        assert "apt-get" not in instructions(self.render(db_type="mongodb"))
        assert "apt-get" not in instructions(self.render(db_type="sqlite"))

    def test_deps_manifest_precedes_source_copy(self):
        content = self.render()
        assert content.index("COPY requirements.txt .") < content.index(
            "RUN pip install --no-cache-dir --user"
        )
        assert content.index("RUN pip install --no-cache-dir --user") < content.index(
            "COPY --chown=app:app . ."
        )

    def test_non_root_system_user(self):
        content = self.render()
        assert "addgroup --system app" in content
        assert "adduser --system --ingroup app" in content
        assert "--disabled-password" not in instructions(content)
        assert "\nUSER app\n" in content

    def test_healthcheck_uses_urllib_not_curl(self):
        content = self.render()
        assert "HEALTHCHECK" in content
        assert "urllib.request" in content
        assert "curl" not in instructions(content)

    def test_exec_form_cmd_and_expose(self):
        content = self.render()
        assert 'CMD ["uvicorn", "main:app"' in content
        assert "EXPOSE 8000" in content
        # Production CMD must not carry --reload; dev compose overrides it.
        assert "--reload" not in instructions(content)

    def test_documents_init_without_installing_tini(self):
        content = self.render()
        # --init is documented in a comment; tini is named only to explain why
        # it is deliberately absent, and must never actually be installed.
        assert "--init" in content
        assert "tini" in content
        assert "tini" not in instructions(content)


# ---------------------------------------------------------------------------
# .dockerignore template
# ---------------------------------------------------------------------------


class TestDockerignoreTemplate:
    @pytest.fixture
    def content(self) -> str:
        return docker_render.render_files(make_state(), with_compose=False)[
            ".dockerignore"
        ]

    @pytest.mark.parametrize(
        "pattern",
        [
            ".git",
            ".gitignore",
            "__pycache__/",
            "*.py[cod]",
            "*.egg-info/",
            "dist/",
            "build/",
            "*.whl",
            "venv/",
            ".venv/",
            ".env",
            ".env.*",
            ".kaira.json",
            ".vscode/",
            ".idea/",
            "*.swp",
            "Dockerfile",
            "docker-compose*.yml",
            "tests/",
            "docs/",
            "*.md",
            "LICENSE",
            ".DS_Store",
            "Thumbs.db",
        ],
    )
    def test_excludes_pattern(self, content, pattern):
        assert pattern in content.splitlines()

    def test_env_example_explicitly_kept(self, content):
        lines = content.splitlines()
        assert "!.env.example" in lines
        # The negation must come after the rule it overrides.
        assert lines.index(".env.*") < lines.index("!.env.example")


# ---------------------------------------------------------------------------
# Dynamic compose rendering
# ---------------------------------------------------------------------------


class TestComposeServices:
    def compose(self, prod: bool = False, **overrides) -> dict:
        files = docker_render.render_files(make_state(**overrides), with_compose=True)
        name = "docker-compose.prod.yml" if prod else "docker-compose.yml"
        return yaml.safe_load(files[name])

    @pytest.mark.parametrize("prod", [False, True])
    def test_valid_yaml_without_obsolete_version_key(self, prod):
        doc = self.compose(prod=prod)
        assert "version" not in doc
        assert "app" in doc["services"]

    @pytest.mark.parametrize(
        "db_type,has_db",
        [
            ("postgresql", True),
            ("mysql", True),
            ("mongodb", True),
            ("sqlite", False),
            ("supabase", False),
            ("atlas", False),
            ("firebase", False),
        ],
    )
    def test_database_service_presence(self, db_type, has_db):
        services = self.compose(db_type=db_type)["services"]
        assert ("db" in services) is has_db

    def test_cache_adds_redis(self):
        assert "redis" not in self.compose(cache=False)["services"]
        assert "redis" in self.compose(cache=True)["services"]

    def test_task_adds_worker_and_broker(self):
        services = self.compose(task=True)["services"]
        assert "worker" in services
        assert "redis" in services

    def test_cache_and_task_share_one_redis(self):
        services = self.compose(cache=True, task=True)["services"]
        redis_services = [name for name in services if "redis" in name]
        assert redis_services == ["redis"]

    @pytest.mark.parametrize("provider", ["elasticsearch", "meilisearch"])
    def test_search_provider_adds_its_engine(self, provider):
        services = self.compose(search=provider)["services"]
        assert "search" in services
        assert provider.split("search")[0] in services["search"]["image"].lower()

    def test_no_search_service_without_provider(self):
        assert "search" not in self.compose()["services"]

    def test_monitor_needs_no_compose_service(self):
        # Sentry is env wiring only — it must not add a container.
        without = set(self.compose()["services"])
        with_sentry = set(self.compose(monitor="sentry")["services"])
        assert without == with_sentry

    def test_every_service_declares_its_volume(self):
        doc = self.compose(cache=True, task=True, search="elasticsearch")
        declared = set(doc.get("volumes") or {})
        assert {"pgdata", "redisdata", "esdata"} <= declared


class TestDevCompose:
    @pytest.fixture
    def doc(self) -> dict:
        files = docker_render.render_files(
            make_state(cache=True, task=True), with_compose=True
        )
        return yaml.safe_load(files["docker-compose.yml"])

    def test_app_overrides_cmd_with_reload(self, doc):
        assert "--reload" in doc["services"]["app"]["command"]

    def test_uses_development_env_file(self, doc):
        assert doc["services"]["app"]["env_file"] == [".env.development"]

    def test_volume_mount_excludes_venv(self, doc):
        volumes = doc["services"]["app"]["volumes"]
        assert ".:/app" in volumes
        assert "/app/.venv" in volumes

    def test_depends_on_uses_service_healthy(self, doc):
        for dep in doc["services"]["app"]["depends_on"].values():
            assert dep["condition"] == "service_healthy"

    def test_app_is_hardened(self, doc):
        app_svc = doc["services"]["app"]
        assert app_svc["read_only"] is True
        assert "no-new-privileges:true" in app_svc["security_opt"]


class TestProdCompose:
    @pytest.fixture
    def doc(self) -> dict:
        files = docker_render.render_files(
            make_state(cache=True, task=True), with_compose=True
        )
        return yaml.safe_load(files["docker-compose.prod.yml"])

    def test_read_only_and_tmpfs_on_app(self, doc):
        app_svc = doc["services"]["app"]
        assert app_svc["read_only"] is True
        assert any("size=" in mount for mount in app_svc["tmpfs"])

    def test_no_new_privileges_on_every_service(self, doc):
        for name, svc in doc["services"].items():
            assert "no-new-privileges:true" in svc["security_opt"], name

    def test_log_rotation_on_every_service(self, doc):
        for name, svc in doc["services"].items():
            assert svc["logging"]["driver"] == "json-file", name
            assert svc["logging"]["options"]["max-size"], name
            assert svc["logging"]["options"]["max-file"], name

    def test_resource_limits_and_restart_preserved(self, doc):
        app_svc = doc["services"]["app"]
        assert app_svc["deploy"]["resources"]["limits"]["memory"]
        assert app_svc["deploy"]["resources"]["limits"]["cpus"]
        assert app_svc["restart"] == "always"

    def test_uses_production_env_file(self, doc):
        assert doc["services"]["app"]["env_file"] == [".env.production"]

    def test_backing_services_not_published_to_host(self, doc):
        for name in ("db", "redis"):
            assert "ports" not in doc["services"][name]

    def test_no_source_bind_mount(self, doc):
        assert "volumes" not in doc["services"]["app"]


# ---------------------------------------------------------------------------
# Registry extensibility
# ---------------------------------------------------------------------------


class TestServiceRegistry:
    def test_rendering_is_loop_based_over_the_registry(self):
        state = make_state(cache=True, task=True, search="meilisearch")
        names = [svc["name"] for svc in docker_state.build_services(state, "dev")]
        assert names == ["app", "db", "redis", "worker", "search"]

    def test_new_feature_plugs_in_without_template_changes(self):
        """A future feature is one registry entry — no template edit required."""

        def build_rabbit(state, env):
            return [
                docker_state._service(
                    "rabbitmq",
                    env=env,
                    image="rabbitmq:3.13-alpine",
                    ports=["5672:5672"],
                    volume_names=["rabbitdata"],
                )
            ]

        entry = docker_state.ServiceDefinition("rabbit", build_rabbit)
        docker_state.SERVICE_REGISTRY.append(entry)
        try:
            doc = yaml.safe_load(
                docker_render.render_files(make_state(), with_compose=True)[
                    "docker-compose.yml"
                ]
            )
            assert "rabbitmq" in doc["services"]
            assert "rabbitdata" in doc["volumes"]
        finally:
            docker_state.SERVICE_REGISTRY.remove(entry)

    def test_disabled_feature_builders_return_nothing(self):
        state = make_state(db_type="sqlite", cache=False, task=False, search="")
        assert docker_state.build_redis(state, "dev") == []
        assert docker_state.build_worker(state, "dev") == []
        assert docker_state.build_search(state, "dev") == []
        assert docker_state.build_database(state, "dev") == []


# ---------------------------------------------------------------------------
# Feature detection from disk
# ---------------------------------------------------------------------------


class TestFeatureDetection:
    def test_detects_scaffolded_cache(self, tmp_path):
        assert docker_state.detect_cache(tmp_path) is False
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "cache.py").write_text("", encoding="utf-8")
        assert docker_state.detect_cache(tmp_path) is True

    def test_detects_scaffolded_celery(self, tmp_path):
        assert docker_state.detect_task(tmp_path) is False
        (tmp_path / "tasks").mkdir()
        (tmp_path / "tasks" / "celery_app.py").write_text("", encoding="utf-8")
        assert docker_state.detect_task(tmp_path) is True

    def test_detects_search_integration(self, tmp_path):
        assert docker_state.detect_search(tmp_path) == ""
        provider = tmp_path / "integrations" / "search" / "meilisearch"
        provider.mkdir(parents=True)
        (provider / "service.py").write_text("", encoding="utf-8")
        assert docker_state.detect_search(tmp_path) == "meilisearch"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


class TestDockerInit:
    def test_generates_the_full_surface(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            result = run("docker", "init", "--with-compose", "--force")
            assert result.exit_code == 0
            for name in (
                "Dockerfile",
                ".dockerignore",
                "docker-compose.yml",
                "docker-compose.prod.yml",
            ):
                assert (cwd / name).is_file(), name

    def test_dockerfile_only_without_compose_flag(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            result = run("docker", "init", "--force")
            assert result.exit_code == 0
            assert (cwd / "Dockerfile").is_file()
            assert not (cwd / "docker-compose.yml").exists()

    def test_python_flag_pins_the_base_image(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            result = run("docker", "init", "--python", "3.11", "--force")
            assert result.exit_code == 0
            assert "ARG PYTHON_VERSION=3.11." in (cwd / "Dockerfile").read_text(
                encoding="utf-8"
            )

    def test_invalid_python_is_a_smart_error(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            result = run("docker", "init", "--python", "3.7", "--force")
            assert result.exit_code == 1
            assert "3.12" in result.output

    def test_compose_reflects_state_at_init_time(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql", cache_enabled=True)
            result = run("docker", "init", "--with-compose", "--force")
            assert result.exit_code == 0
            doc = yaml.safe_load(
                (cwd / "docker-compose.yml").read_text(encoding="utf-8")
            )
            assert "redis" in doc["services"]

    def test_records_docker_state_in_config(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            assert config["docker_enabled"] is True
            assert config["docker_compose"] is True
            assert config["docker_python"]


class TestDockerSync:
    def test_reports_up_to_date_and_writes_nothing(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            before = (cwd / "docker-compose.yml").read_text(encoding="utf-8")

            result = run("docker", "sync")
            assert result.exit_code == 0
            assert "up to date" in result.output
            assert (cwd / "docker-compose.yml").read_text(encoding="utf-8") == before

    def test_regenerates_after_a_state_change(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["task_enabled"] = True
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            result = run("docker", "sync", "--force")
            assert result.exit_code == 0
            doc = yaml.safe_load(
                (cwd / "docker-compose.yml").read_text(encoding="utf-8")
            )
            assert "worker" in doc["services"]
            assert "redis" in doc["services"]

    def test_dry_run_writes_nothing(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            before = (cwd / "docker-compose.yml").read_text(encoding="utf-8")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["cache_enabled"] = True
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            result = run("docker", "sync", "--dry-run")
            assert result.exit_code == 0
            assert (cwd / "docker-compose.yml").read_text(encoding="utf-8") == before

    def test_db_switch_changes_both_dockerfile_and_compose(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            assert "libpq-dev" in (cwd / "Dockerfile").read_text(encoding="utf-8")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["db_type"] = "mongodb"
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            run("docker", "sync", "--force")
            dockerfile = (cwd / "Dockerfile").read_text(encoding="utf-8")
            assert "libpq-dev" not in instructions(dockerfile)
            assert "apt-get" not in instructions(dockerfile)
            doc = yaml.safe_load(
                (cwd / "docker-compose.yml").read_text(encoding="utf-8")
            )
            assert "mongo" in doc["services"]["db"]["image"]

    def test_errors_without_a_dockerfile(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            result = run("docker", "sync")
            assert result.exit_code == 1
            assert "docker init" in result.output


class TestDriftDetection:
    def test_clean_project_is_in_sync(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            assert docker_render.is_out_of_sync(cwd) is False

    def test_state_change_creates_drift(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["cache_enabled"] = True
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            assert docker_render.is_out_of_sync(cwd) is True

    def test_project_without_docker_never_drifts(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            assert docker_render.is_out_of_sync(Path.cwd()) is False

    def test_autosync_is_a_no_op_without_docker(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            assert docker_render.maybe_autosync(quiet=True) is False

    def test_autosync_defers_to_manual_sync_when_quiet(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            before = (cwd / "docker-compose.yml").read_text(encoding="utf-8")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["cache_enabled"] = True
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            assert docker_render.maybe_autosync(quiet=True) is False
            assert (cwd / "docker-compose.yml").read_text(encoding="utf-8") == before


class TestDockerCommandSurface:
    @pytest.mark.parametrize(
        "command", ["up", "down", "scan", "sync", "status", "init", "build", "run"]
    )
    def test_command_is_registered(self, command):
        result = run("docker", command, "--help")
        assert result.exit_code == 0

    def test_scan_never_pulls_remotely_by_default(self):
        result = run("docker", "scan", "--help")
        assert "--remote" in result.output

    def test_run_enables_init_by_default(self):
        from kaira.commands.docker_cmd import docker_run

        defaults = docker_run.__defaults__ or ()
        assert True in defaults  # --init/--no-init defaults to True


class TestScannerParsers:
    def test_trivy_output(self):
        from kaira.commands.docker_cmd import _parse_trivy

        payload = json.dumps(
            {
                "Results": [
                    {
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2024-0001",
                                "PkgName": "openssl",
                                "InstalledVersion": "3.0.1",
                                "Severity": "HIGH",
                                "FixedVersion": "3.0.2",
                            }
                        ]
                    }
                ]
            }
        )
        findings = _parse_trivy(payload)
        assert findings == [
            {
                "id": "CVE-2024-0001",
                "package": "openssl",
                "installed": "3.0.1",
                "severity": "HIGH",
                "fixed": "3.0.2",
            }
        ]

    def test_grype_output(self):
        from kaira.commands.docker_cmd import _parse_grype

        payload = json.dumps(
            {
                "matches": [
                    {
                        "vulnerability": {
                            "id": "GHSA-xxxx",
                            "severity": "Critical",
                            "fix": {"versions": ["2.0.0"]},
                        },
                        "artifact": {"name": "requests", "version": "1.0.0"},
                    }
                ]
            }
        )
        findings = _parse_grype(payload)
        assert findings[0]["severity"] == "CRITICAL"
        assert findings[0]["fixed"] == "2.0.0"

    def test_scout_sarif_output(self):
        from kaira.commands.docker_cmd import _parse_scout_sarif

        payload = json.dumps(
            {
                "runs": [
                    {
                        "tool": {
                            "driver": {
                                "rules": [
                                    {
                                        "id": "CVE-2024-9999",
                                        "properties": {
                                            "cvssV3_severity": "CRITICAL",
                                            "purls": [
                                                "pkg:deb/debian/shadow@1%3A4.13?arch=amd64"
                                            ],
                                            "fixed_version": "1:4.14",
                                        },
                                    }
                                ]
                            }
                        },
                        "results": [{"ruleId": "CVE-2024-9999"}],
                    }
                ]
            }
        )
        findings = _parse_scout_sarif(payload)
        assert findings[0]["package"] == "shadow"
        assert findings[0]["installed"] == "1:4.13"
        assert findings[0]["severity"] == "CRITICAL"

    def test_malformed_output_yields_no_findings(self):
        from kaira.commands.docker_cmd import (
            _parse_grype,
            _parse_scout_sarif,
            _parse_trivy,
        )

        for parser in (_parse_trivy, _parse_grype, _parse_scout_sarif):
            assert parser("not json") == []

    def test_build_failure_hints_are_actionable(self):
        from kaira.commands.docker_cmd import _build_failure_hint

        context, fix = _build_failure_hint(
            "ERROR: requirements.txt: no such file or directory"
        )
        assert "requirements.txt" in context
        assert fix

        context, fix = _build_failure_hint("Temporary failure in name resolution")
        assert "network" in context.lower()

    def test_build_failure_ignores_docker_desktop_dashboard_link(self):
        """Regression: the desktop-linux builder's trailing dashboard link is
        not an error and must never be surfaced as the failure explanation.
        """
        from kaira.commands.docker_cmd import _build_failure_hint

        output = (
            "#4 [builder 2/5] RUN apt-get update && apt-get install -y gcc\n"
            "#4 ERROR: process did not complete successfully: exit code: 100\n"
            "\n"
            'ERROR: failed to solve: process "/bin/sh -c apt-get update && '
            'apt-get install -y gcc" did not complete successfully: exit code: 100\n'
            "View build details: docker-desktop://dashboard/build/desktop-linux/"
            "desktop-linux/imtl37956ckwyt9lp7gd8we6j\n"
        )
        context, fix = _build_failure_hint(output)
        assert "docker-desktop://" not in context
        assert "View build details" not in context
        assert "exit code: 100" in context
        assert fix

    def test_build_failure_falls_back_when_no_error_line_present(self):
        from kaira.commands.docker_cmd import _build_failure_hint

        output = (
            "Successfully built abc123\n"
            "View build details: docker-desktop://dashboard/build/x/y/z\n"
        )
        context, _ = _build_failure_hint(output)
        assert "docker-desktop://" not in context
        assert context == "Successfully built abc123"


# ---------------------------------------------------------------------------
# Commands that talk to a Docker daemon — mocked, so these run without one.
# ---------------------------------------------------------------------------


def contains(*parts: str) -> Callable[[list], bool]:
    """Predicate: every part appears somewhere in the argv list."""
    return lambda cmd: all(part in cmd for part in parts)


class FakeRun:
    """Routes ``docker_cmd._run()`` calls to canned results by argv match.

    Routes are matched in the order they were registered; the first
    predicate that matches wins.  Unmatched commands succeed with empty
    output, which is enough for calls the test does not care about (e.g. the
    daemon reachability check every command opens with).
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._routes: list[
            tuple[Callable[[list], bool], subprocess.CompletedProcess]
        ] = []

    def when(
        self,
        predicate: Callable[[list], bool],
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> FakeRun:
        self._routes.append(
            (predicate, subprocess.CompletedProcess([], returncode, stdout, stderr))
        )
        return self

    def __call__(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        for predicate, result in self._routes:
            if predicate(cmd):
                return result
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def fake_run(monkeypatch):
    """Replace docker_cmd's subprocess runner and docker/scanner discovery."""
    from kaira.commands import docker_cmd

    router = FakeRun()
    monkeypatch.setattr(docker_cmd, "_run", router)
    monkeypatch.setattr(docker_cmd.shutil, "which", lambda name: f"/usr/bin/{name}")
    return router


class TestPreflightChecks:
    def test_docker_cli_missing(self, tmp_path, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(docker_cmd.shutil, "which", lambda name: None)
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "build")
            assert result.exit_code == 1
            assert "docker" in result.output.lower()

    def test_daemon_not_running(self, tmp_path, fake_run):
        fake_run.when(contains("info"), returncode=1)
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "build")
            assert result.exit_code == 1
            assert "not running" in result.output.lower()


class TestDockerBuildMocked:
    def test_no_dockerfile(self, tmp_path, fake_run):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            result = run("docker", "build")
            assert result.exit_code == 1
            assert "docker init" in result.output

    def test_build_failure_shows_hint(self, tmp_path, fake_run):
        fake_run.when(
            contains("build", "-t"),
            returncode=1,
            stderr="ERROR: requirements.txt: no such file or directory",
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--force")
            result = run("docker", "build")
            assert result.exit_code == 1
            assert "requirements.txt" in result.output

    def test_build_success_reports_size(self, tmp_path, fake_run):
        fake_run.when(contains("build", "-t"), returncode=0)
        fake_run.when(contains("image", "ls"), stdout="123MB\n")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--force")
            result = run("docker", "build")
            assert result.exit_code == 0
            assert "123MB" in result.output

    def test_verbose_streams_and_reports_failure(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.subprocess,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1),
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--force")
            result = run("docker", "build", "--verbose")
            assert result.exit_code == 1


class TestDockerRunMocked:
    def test_run_failure(self, tmp_path, fake_run):
        fake_run.when(
            contains("run", "-d"),
            returncode=1,
            stderr="Error: port is already allocated",
        )
        fake_run.when(contains("version", "--format"), stdout="27.3.1")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "run", "--tag", "demo")
            assert result.exit_code == 1
            assert "allocated" in result.output.lower()

    def test_run_success_reports_container_and_url(self, tmp_path, fake_run):
        fake_run.when(contains("run", "-d"), stdout="abcdef1234567890\n")
        fake_run.when(contains("version", "--format"), stdout="27.3.1")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "run", "--tag", "demo", "--port", "9000")
            assert result.exit_code == 0
            assert "abcdef123456" in result.output
            assert "9000" in result.output

    def test_old_docker_falls_back_without_init(self, tmp_path, fake_run):
        fake_run.when(contains("run", "-d"), stdout="abc\n")
        fake_run.when(contains("version", "--format"), stdout="17.03.0")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "run", "--tag", "demo")
            assert result.exit_code == 0
            assert "not available" in result.output.lower()

    def test_missing_env_file_is_noted_not_fatal(self, tmp_path, fake_run):
        fake_run.when(contains("run", "-d"), stdout="abc\n")
        fake_run.when(contains("version", "--format"), stdout="27.3.1")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "run", "--tag", "demo", "--env-file", ".env.missing")
            assert result.exit_code == 0
            assert ".env.missing" in result.output


class TestDockerUpMocked:
    def test_no_compose_file(self, tmp_path, fake_run):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            result = run("docker", "up")
            assert result.exit_code == 1
            assert "with-compose" in result.output

    def test_dev_foreground_success(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.subprocess,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0),
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "up")
            assert result.exit_code == 0
            assert "stopped" in result.output.lower()

    def test_dev_foreground_failure_propagates_exit_code(
        self, tmp_path, fake_run, monkeypatch
    ):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.subprocess,
            "run",
            lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3),
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "up")
            assert result.exit_code == 3

    def test_prod_requires_correct_typed_confirmation(
        self, tmp_path, fake_run, monkeypatch
    ):
        import typer as typer_module

        monkeypatch.setattr(typer_module, "prompt", lambda *a, **k: "wrong-name")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "up", "--prod")
            assert result.exit_code == 1
            assert "aborted" in result.output.lower()

    def test_prod_confirmed_starts_detached_and_reports_services(
        self, tmp_path, fake_run, monkeypatch
    ):
        import typer as typer_module

        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")

            monkeypatch.setattr(typer_module, "prompt", lambda *a, **k: cwd.name)
            fake_run.when(contains("compose", "up"), returncode=0)
            fake_run.when(
                contains("compose", "ps"),
                stdout=json.dumps(
                    [{"Service": "app", "State": "running", "Health": "healthy"}]
                ),
            )
            result = run("docker", "up", "--prod")
            assert result.exit_code == 0
            assert "app" in result.output

    def test_compose_up_failure_is_a_smart_error(self, tmp_path, fake_run):
        fake_run.when(
            contains("compose", "up"), returncode=1, stderr="pull access denied"
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "up", "--detach")
            assert result.exit_code == 1
            assert "pull access denied" in result.output


class TestDockerDownMocked:
    def test_no_compose_file(self, tmp_path, fake_run):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            result = run("docker", "down")
            assert result.exit_code == 1

    def test_down_success(self, tmp_path, fake_run):
        fake_run.when(contains("compose", "down"), returncode=0)
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "down")
            assert result.exit_code == 0
            assert "stopped" in result.output.lower()

    def test_down_failure_is_smart_error(self, tmp_path, fake_run):
        fake_run.when(
            contains("compose", "down"), returncode=1, stderr="network not found"
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "down")
            assert result.exit_code == 1
            assert "network not found" in result.output

    def test_volumes_blocked_in_production(self, tmp_path, fake_run, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "down", "--volumes")
            assert result.exit_code == 1
            assert "production" in result.output.lower()

    def test_volumes_with_force_destroys(self, tmp_path, fake_run, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        fake_run.when(contains("compose", "down", "--volumes"), returncode=0)
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd)
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "down", "--volumes", "--force")
            assert result.exit_code == 0
            assert "destroyed" in result.output.lower()


class TestDockerStatusMocked:
    def test_no_compose_file(self, tmp_path, fake_run):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            write_project(Path.cwd())
            result = run("docker", "status")
            assert result.exit_code == 1

    def test_no_containers_running(self, tmp_path, fake_run):
        fake_run.when(contains("compose", "ps"), stdout="")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            result = run("docker", "status")
            assert result.exit_code == 0
            assert "none running" in result.output.lower()

    def test_reports_services_image_and_volumes(self, tmp_path, fake_run):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")

            slug = cwd.name.lower().replace("-", "_").replace(" ", "_")
            fake_run.when(
                contains("compose", "ps"),
                stdout=json.dumps(
                    [
                        {
                            "Service": "app",
                            "State": "running",
                            "Health": "healthy",
                            "RunningFor": "2 minutes",
                            "Image": "demo-api:latest",
                            "Publishers": [{"PublishedPort": 8000, "TargetPort": 8000}],
                        }
                    ]
                ),
            )
            fake_run.when(contains("image", "ls"), stdout="120MB\n")
            fake_run.when(
                contains("system", "df"),
                stdout=json.dumps([{"Name": f"{slug}_pgdata", "Size": "45MB"}]),
            )
            result = run("docker", "status")
            assert result.exit_code == 0
            assert "8000" in result.output
            assert "45MB" in result.output


class TestDockerScanMocked:
    def _no_scout(self, fake_run):
        fake_run.when(contains("scout", "version"), returncode=1)

    def test_no_scanner_available(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/docker" if name == "docker" else None,
        )
        self._no_scout(fake_run)
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan")
            assert result.exit_code == 1
            assert "trivy" in result.output.lower()

    def test_image_not_local_without_remote(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/trivy" if name in ("trivy", "docker") else None,
        )
        self._no_scout(fake_run)
        fake_run.when(contains("image", "inspect"), returncode=1)
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan", "--tag", "ghost-image")
            assert result.exit_code == 1
            assert "not present locally" in result.output.lower()

    def test_remote_flag_skips_local_image_check(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/trivy" if name in ("trivy", "docker") else None,
        )
        self._no_scout(fake_run)
        fake_run.when(contains("trivy", "image"), stdout=json.dumps({"Results": []}))
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan", "--tag", "remote/image:tag", "--remote")
            assert result.exit_code == 0
        assert not any("inspect" in call for call in fake_run.calls)

    def test_clean_scan_reports_no_vulnerabilities(
        self, tmp_path, fake_run, monkeypatch
    ):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/trivy" if name in ("trivy", "docker") else None,
        )
        self._no_scout(fake_run)
        fake_run.when(contains("image", "inspect"), returncode=0)
        fake_run.when(contains("trivy", "image"), stdout=json.dumps({"Results": []}))
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan", "--tag", "kaira-app")
            assert result.exit_code == 0
            assert "no known vulnerabilities" in result.output.lower()

    def test_low_only_findings_do_not_fail(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/trivy" if name in ("trivy", "docker") else None,
        )
        self._no_scout(fake_run)
        fake_run.when(contains("image", "inspect"), returncode=0)
        fake_run.when(
            contains("trivy", "image"),
            stdout=json.dumps(
                {
                    "Results": [
                        {
                            "Vulnerabilities": [
                                {
                                    "VulnerabilityID": "CVE-1",
                                    "PkgName": "libc",
                                    "InstalledVersion": "1",
                                    "Severity": "LOW",
                                    "FixedVersion": "2",
                                }
                            ]
                        }
                    ]
                }
            ),
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan", "--tag", "kaira-app")
            assert result.exit_code == 0
            assert "libc" in result.output

    def test_high_severity_fails_the_command(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/trivy" if name in ("trivy", "docker") else None,
        )
        self._no_scout(fake_run)
        fake_run.when(contains("image", "inspect"), returncode=0)
        fake_run.when(
            contains("trivy", "image"),
            stdout=json.dumps(
                {
                    "Results": [
                        {
                            "Vulnerabilities": [
                                {
                                    "VulnerabilityID": "CVE-2",
                                    "PkgName": "openssl",
                                    "InstalledVersion": "1",
                                    "Severity": "CRITICAL",
                                    "FixedVersion": "2",
                                }
                            ]
                        }
                    ]
                }
            ),
        )
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan", "--tag", "kaira-app", "--fix")
            assert result.exit_code == 1
            assert "openssl" in result.output

    def test_scanner_failure_is_a_smart_error(self, tmp_path, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/trivy" if name in ("trivy", "docker") else None,
        )
        self._no_scout(fake_run)
        fake_run.when(contains("image", "inspect"), returncode=0)
        fake_run.when(contains("trivy", "image"), returncode=1, stderr="unauthorized")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run("docker", "scan", "--tag", "kaira-app")
            assert result.exit_code == 1
            assert "unauthorized" in result.output.lower()


class TestScannerResolution:
    def test_prefers_scout_when_available(self, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/docker" if name == "docker" else None,
        )
        fake_run.when(contains("scout", "version"), returncode=0)
        assert docker_cmd._resolve_scanner() == "scout"

    def test_falls_back_to_trivy(self, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: (
                "/usr/bin/trivy"
                if name == "trivy"
                else ("/usr/bin/docker" if name == "docker" else None)
            ),
        )
        fake_run.when(contains("scout", "version"), returncode=1)
        assert docker_cmd._resolve_scanner() == "trivy"

    def test_falls_back_to_grype(self, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(
            docker_cmd.shutil,
            "which",
            lambda name: "/usr/bin/grype" if name == "grype" else None,
        )
        fake_run.when(contains("scout", "version"), returncode=1)
        assert docker_cmd._resolve_scanner() == "grype"

    def test_none_available(self, fake_run, monkeypatch):
        from kaira.commands import docker_cmd

        monkeypatch.setattr(docker_cmd.shutil, "which", lambda name: None)
        assert docker_cmd._resolve_scanner() is None


class TestComposeHelpers:
    def test_json_array_output(self, fake_run):
        from kaira.commands.docker_cmd import _compose_services_status

        fake_run.when(
            contains("ps", "--format", "json"), stdout=json.dumps([{"Service": "app"}])
        )
        rows = _compose_services_status(Path("docker-compose.yml"), ".env.development")
        assert rows == [{"Service": "app"}]

    def test_ndjson_output(self, fake_run):
        from kaira.commands.docker_cmd import _compose_services_status

        fake_run.when(
            contains("ps", "--format", "json"),
            stdout='{"Service": "app"}\n{"Service": "db"}\n',
        )
        rows = _compose_services_status(Path("docker-compose.yml"), ".env.development")
        assert [row["Service"] for row in rows] == ["app", "db"]

    def test_malformed_output_yields_no_rows(self, fake_run):
        from kaira.commands.docker_cmd import _compose_services_status

        fake_run.when(contains("ps", "--format", "json"), stdout="not json at all")
        assert (
            _compose_services_status(Path("docker-compose.yml"), ".env.development")
            == []
        )

    def test_failure_yields_no_rows(self, fake_run):
        from kaira.commands.docker_cmd import _compose_services_status

        fake_run.when(contains("ps", "--format", "json"), returncode=1)
        assert (
            _compose_services_status(Path("docker-compose.yml"), ".env.development")
            == []
        )

    def test_format_ports_with_and_without_publishers(self):
        from kaira.commands.docker_cmd import _format_ports

        assert _format_ports({}) == "—"
        row = {
            "Publishers": [
                {"PublishedPort": 8000, "TargetPort": 8000},
                {"PublishedPort": 0},
            ]
        }
        assert _format_ports(row) == "8000→8000"

    def test_volume_sizes_malformed_output(self, fake_run):
        from kaira.commands.docker_cmd import _volume_sizes

        fake_run.when(contains("system", "df"), stdout="garbage")
        assert _volume_sizes() == {}

    def test_volume_sizes_command_failure(self, fake_run):
        from kaira.commands.docker_cmd import _volume_sizes

        fake_run.when(contains("system", "df"), returncode=1)
        assert _volume_sizes() == {}

    def test_image_size_fallback_on_failure(self, fake_run):
        from kaira.commands.docker_cmd import _image_size

        fake_run.when(contains("image", "ls"), returncode=1)
        assert _image_size("demo") == "—"

    def test_supports_init_flag_new_version(self, fake_run):
        from kaira.commands.docker_cmd import _supports_init_flag

        fake_run.when(contains("version", "--format"), stdout="17.06.0")
        assert _supports_init_flag() is True

    def test_supports_init_flag_old_version(self, fake_run):
        from kaira.commands.docker_cmd import _supports_init_flag

        fake_run.when(contains("version", "--format"), stdout="17.05.0")
        assert _supports_init_flag() is False

    def test_supports_init_flag_command_failure(self, fake_run):
        from kaira.commands.docker_cmd import _supports_init_flag

        fake_run.when(contains("version", "--format"), returncode=1)
        assert _supports_init_flag() is False

    def test_compose_cmd_includes_env_file_only_when_present(self, tmp_path):
        from kaira.commands.docker_cmd import _compose_cmd

        with runner.isolated_filesystem(temp_dir=tmp_path):
            cmd = _compose_cmd(Path("docker-compose.yml"), ".env.development")
            assert "--env-file" not in cmd

            Path(".env.development").write_text("", encoding="utf-8")
            cmd = _compose_cmd(Path("docker-compose.yml"), ".env.development")
            assert "--env-file" in cmd


# ---------------------------------------------------------------------------
# docker_render interactive paths — gated on is_interactive(), so they never
# fire through the CliRunner (stdout is never a real tty there) and need
# direct monkeypatching to exercise.
# ---------------------------------------------------------------------------


class TestDockerRenderInteractivePaths:
    def test_prompt_action_uses_questionary_when_available(self, monkeypatch):
        import questionary

        class FakePrompt:
            def ask(self):
                return "o"

        monkeypatch.setattr(questionary, "select", lambda *a, **k: FakePrompt())
        plan = docker_render.FilePlan(
            path=Path("Dockerfile"), content="x", status="changed"
        )
        assert docker_render._prompt_action(plan) == "o"

    def test_prompt_action_falls_back_to_plain_prompt(self, monkeypatch):
        import questionary
        from rich.prompt import Prompt

        def boom(*a, **k):
            raise RuntimeError("no tty")

        monkeypatch.setattr(questionary, "select", boom)
        monkeypatch.setattr(Prompt, "ask", lambda *a, **k: "s")
        plan = docker_render.FilePlan(
            path=Path("Dockerfile"), content="x", status="changed"
        )
        assert docker_render._prompt_action(plan) == "s"

    def test_show_diff_no_op_for_identical_content(self, tmp_path):
        path = tmp_path / "Dockerfile"
        path.write_text("same", encoding="utf-8")
        plan = docker_render.FilePlan(path=path, content="same", status="same")
        docker_render.show_diff(plan)  # must not raise

    def test_apply_plan_skips_plans_that_need_no_write(self, tmp_path):
        path = tmp_path / "Dockerfile"
        path.write_text("same", encoding="utf-8")
        plan = docker_render.FilePlan(path=path, content="same", status="same")
        assert docker_render.apply_plan([plan]) == (0, 0)

    def test_apply_plan_interactive_view_then_overwrite(self, tmp_path, monkeypatch):
        monkeypatch.setattr(docker_render, "is_interactive", lambda: True)
        responses = iter(["v", "o"])
        monkeypatch.setattr(
            docker_render, "_prompt_action", lambda plan: next(responses)
        )
        path = tmp_path / "Dockerfile"
        path.write_text("old", encoding="utf-8")
        plan = docker_render.FilePlan(path=path, content="new", status="changed")
        written, skipped = docker_render.apply_plan([plan])
        assert (written, skipped) == (1, 0)
        assert path.read_text(encoding="utf-8") == "new"

    def test_apply_plan_interactive_skip_leaves_file_untouched(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(docker_render, "is_interactive", lambda: True)
        monkeypatch.setattr(docker_render, "_prompt_action", lambda plan: "s")
        path = tmp_path / "Dockerfile"
        path.write_text("old", encoding="utf-8")
        plan = docker_render.FilePlan(path=path, content="new", status="changed")
        written, skipped = docker_render.apply_plan([plan])
        assert (written, skipped) == (0, 1)
        assert path.read_text(encoding="utf-8") == "old"

    def test_maybe_autosync_no_pending_changes(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            assert docker_render.maybe_autosync() is False

    def test_maybe_autosync_interactive_confirm_yes_regenerates(
        self, tmp_path, monkeypatch
    ):
        from rich.prompt import Prompt

        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["cache_enabled"] = True
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            monkeypatch.setattr(docker_render, "is_interactive", lambda: True)
            monkeypatch.setattr(Prompt, "ask", lambda *a, **k: "y")

            assert docker_render.maybe_autosync() is True
            doc = yaml.safe_load(
                (cwd / "docker-compose.yml").read_text(encoding="utf-8")
            )
            assert "redis" in doc["services"]

    def test_maybe_autosync_interactive_decline_leaves_files(
        self, tmp_path, monkeypatch
    ):
        from rich.prompt import Prompt

        with runner.isolated_filesystem(temp_dir=tmp_path):
            cwd = Path.cwd()
            write_project(cwd, db_type="postgresql")
            run("docker", "init", "--with-compose", "--force")
            before = (cwd / "docker-compose.yml").read_text(encoding="utf-8")

            config = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            config["cache_enabled"] = True
            (cwd / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

            monkeypatch.setattr(docker_render, "is_interactive", lambda: True)
            monkeypatch.setattr(Prompt, "ask", lambda *a, **k: "n")

            assert docker_render.maybe_autosync() is False
            assert (cwd / "docker-compose.yml").read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# `kaira init --docker` — a second, older Docker scaffold path in project.py
# that must render the same templates without crashing. Regression coverage
# for a real bug: it rendered with the old flat ctx dict, which no longer
# supplies the variables the retrofitted templates require (python_version,
# system_deps, services, ...), raising jinja2.UndefinedError at runtime.
# ---------------------------------------------------------------------------


class TestKairaInitDockerIntegration:
    def test_init_with_docker_does_not_crash(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = run(
                "init",
                "proj-docker",
                "--db",
                "postgresql",
                "--auth",
                "none",
                "--docker",
                "--ci",
                "none",
                "--profile",
                "scale",
                "--yes",
            )
            assert result.exit_code == 0, result.output

            project_dir = Path.cwd() / "proj-docker"
            for name in (
                "Dockerfile",
                ".dockerignore",
                "docker-compose.yml",
                "docker-compose.prod.yml",
            ):
                assert (project_dir / name).is_file(), name

            dockerfile = (project_dir / "Dockerfile").read_text(encoding="utf-8")
            assert "ARG PYTHON_VERSION=3." in dockerfile
            assert "libpq-dev" in dockerfile

            doc = yaml.safe_load(
                (project_dir / "docker-compose.yml").read_text(encoding="utf-8")
            )
            assert "postgres" in doc["services"]["db"]["image"]

    def test_init_docker_state_matches_scaffolded_files(self, tmp_path):
        """A freshly scaffolded project must report as in sync, not drifted."""
        import os

        with runner.isolated_filesystem(temp_dir=tmp_path):
            run(
                "init",
                "proj-sync",
                "--db",
                "mongodb",
                "--auth",
                "none",
                "--docker",
                "--ci",
                "none",
                "--profile",
                "scale",
                "--yes",
            )
            project_dir = Path.cwd() / "proj-sync"

            config = json.loads(
                (project_dir / ".kaira.json").read_text(encoding="utf-8")
            )
            assert config["docker_enabled"] is True
            assert config["docker_compose"] is True
            assert config["docker_python"]

            # docker_state.resolve_state() reads .kaira.json via get_config(),
            # which searches from the real process cwd rather than the `root`
            # argument — exactly like every real `kaira docker *` invocation,
            # which always runs with cwd already inside the project.
            outer_cwd = os.getcwd()
            os.chdir(project_dir)
            try:
                assert docker_render.is_out_of_sync(project_dir) is False
            finally:
                os.chdir(outer_cwd)

    def test_init_without_docker_writes_no_docker_files(self, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            run(
                "init",
                "proj-nodocker",
                "--db",
                "sqlite",
                "--auth",
                "none",
                "--no-docker",
                "--ci",
                "none",
                "--profile",
                "scale",
                "--yes",
            )
            project_dir = Path.cwd() / "proj-nodocker"
            assert not (project_dir / "Dockerfile").exists()
            config = json.loads(
                (project_dir / ".kaira.json").read_text(encoding="utf-8")
            )
            assert config["docker_enabled"] is False
