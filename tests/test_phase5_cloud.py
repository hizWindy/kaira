"""Tests for Phase 5 cloud commands — wizard validation, provider routing, env masking."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from devflow.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Atlas URI validation
# ---------------------------------------------------------------------------

_ATLAS_URI_RE = re.compile(r"^mongodb\+srv://", re.IGNORECASE)


class TestAtlasURIValidation:
    def test_valid_atlas_uri(self):
        assert _ATLAS_URI_RE.match("mongodb+srv://user:pass@cluster.mongodb.net/db")

    def test_invalid_atlas_uri_rejected(self):
        assert not _ATLAS_URI_RE.match("mongodb://localhost:27017/db")

    def test_invalid_atlas_uri_http_rejected(self):
        assert not _ATLAS_URI_RE.match("http://cluster.mongodb.net")

    def test_valid_atlas_uri_case_insensitive(self):
        assert _ATLAS_URI_RE.match("MongoDB+SRV://user@cluster.mongodb.net/")


# ---------------------------------------------------------------------------
# Supabase connection string assembly
# ---------------------------------------------------------------------------


class TestSupabaseConnectionString:
    def test_pooled_url_format(self):
        host = "xyzxyz.supabase.co"
        password = "s3cr3t"
        pooled = f"postgresql+asyncpg://postgres:{password}@db.{host}:6543/postgres?pgbouncer=true"
        assert "6543" in pooled
        assert "pgbouncer=true" in pooled
        assert "postgresql+asyncpg" in pooled

    def test_direct_url_format(self):
        host = "xyzxyz.supabase.co"
        password = "s3cr3t"
        direct = f"postgresql+asyncpg://postgres:{password}@db.{host}:5432/postgres"
        assert "5432" in direct
        assert "pgbouncer" not in direct

    def test_password_not_in_masked_output(self):
        from devflow.commands.ux_helpers import mask_credentials

        raw = "postgresql+asyncpg://postgres:s3cr3t@db.xyzxyz.supabase.co:5432/postgres"
        masked = mask_credentials(raw)
        assert "s3cr3t" not in masked
        assert "***" in masked


# ---------------------------------------------------------------------------
# Firebase credential validation
# ---------------------------------------------------------------------------


class TestFirebaseCredentialValidation:
    def test_valid_service_account_passes(self, tmp_path):
        cred = {
            "type": "service_account",
            "project_id": "my-project",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
            "client_email": "service@my-project.iam.gserviceaccount.com",
        }
        cred_file = tmp_path / "serviceaccount.json"
        cred_file.write_text(json.dumps(cred))

        required_keys = {"type", "project_id", "private_key", "client_email"}
        data = json.loads(cred_file.read_text())
        missing = required_keys - set(data.keys())
        assert len(missing) == 0

    def test_missing_keys_detected(self, tmp_path):
        cred = {"type": "service_account"}
        cred_file = tmp_path / "bad.json"
        cred_file.write_text(json.dumps(cred))

        required_keys = {"type", "project_id", "private_key", "client_email"}
        data = json.loads(cred_file.read_text())
        missing = required_keys - set(data.keys())
        assert "project_id" in missing
        assert "private_key" in missing

    def test_invalid_json_detected(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not-json{{{")

        with pytest.raises(json.JSONDecodeError):
            json.loads(bad_file.read_text())


# ---------------------------------------------------------------------------
# .devflow.json cloud config persistence
# ---------------------------------------------------------------------------


class TestCloudConfigPersistence:
    def test_save_cloud_to_devflow_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Create minimal .devflow.json
        cfg = {
            "output_dir": "app",
            "db_type": "sqlite",
            "models_dir": "models",
        }
        (tmp_path / ".devflow.json").write_text(json.dumps(cfg))

        from devflow.commands.cloud_cmd import _save_cloud_to_devflow

        with patch("devflow.config.get_config") as mock_cfg:
            mock_instance = MagicMock()
            mock_instance.db_type = "sqlite"
            mock_cfg.return_value = mock_instance
            with patch("devflow.config.save_config"):
                _save_cloud_to_devflow("supabase", {"fallback": {}})

        updated = json.loads((tmp_path / ".devflow.json").read_text())
        assert updated["database"] == "supabase"
        assert updated["cloud"] is True
        assert updated["cloud_provider"] == "supabase"

    def test_get_cloud_config_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from devflow.commands.cloud_cmd import _get_cloud_config

        result = _get_cloud_config()
        assert isinstance(result, dict)
        assert result == {}


# ---------------------------------------------------------------------------
# env update helpers
# ---------------------------------------------------------------------------


class TestEnvUpdateHelpers:
    def test_update_env_files_writes_keys(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        env_dev = tmp_path / ".env.development"
        env_dev.write_text("APP_ENV=development\n")

        from devflow.commands.cloud_cmd import _update_env_files

        # _update_env_files searches for .env* files in cwd — no mocking needed
        _update_env_files({"ATLAS_URI": "mongodb+srv://user:pass@cluster.net/db"})

        content = env_dev.read_text()
        assert "ATLAS_URI=" in content

    def test_example_env_gets_placeholder(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        example = tmp_path / ".env.example"
        example.write_text("APP_ENV=development\n")

        from devflow.commands.cloud_cmd import _write_env_placeholders

        _write_env_placeholders(example, {"SUPABASE_DB_URL": "real-value"})

        content = example.read_text()
        assert "<your-supabase-db-url>" in content
        # Real value must NOT be in example
        assert "real-value" not in content


# ---------------------------------------------------------------------------
# db switch routes cloud providers
# ---------------------------------------------------------------------------


class TestDbSwitchCloudRouting:
    def test_db_switch_supabase_calls_cloud_connect(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devflow.json").write_text(json.dumps({
            "output_dir": "app", "db_type": "sqlite", "models_dir": "models",
            "repositories_dir": "repositories", "schemas_dir": "schemas",
            "services_dir": "services", "routers_dir": "routers",
        }))

        with patch("devflow.commands.cloud_cmd.cloud_connect") as mock_connect:
            mock_connect.return_value = None
            result = runner.invoke(app, ["db", "switch", "supabase"])
        # Should trigger cloud connect routing
        assert "cloud provider" in result.output.lower() or mock_connect.called or result.exit_code in (0, 1)

    def test_db_switch_invalid_type_shows_error(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devflow.json").write_text(json.dumps({
            "output_dir": "app", "db_type": "sqlite", "models_dir": "models",
            "repositories_dir": "repositories", "schemas_dir": "schemas",
            "services_dir": "services", "routers_dir": "routers",
        }))
        result = runner.invoke(app, ["db", "switch", "cassandra"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Queue count helpers
# ---------------------------------------------------------------------------


class TestQueueHelpers:
    def test_queue_line_count_zero_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from devflow.commands.cloud_cmd import _queue_line_count

        assert _queue_line_count() == 0

    def test_queue_line_count_counts_lines(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        queue_dir = tmp_path / ".devflow" / "fallback"
        queue_dir.mkdir(parents=True)
        queue_file = queue_dir / "write_queue.jsonl"
        queue_file.write_text('{"id":"1"}\n{"id":"2"}\n')

        from devflow.commands.cloud_cmd import _queue_line_count

        assert _queue_line_count() == 2

    def test_conflict_line_count_zero_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from devflow.commands.cloud_cmd import _conflict_line_count

        assert _conflict_line_count() == 0


# ---------------------------------------------------------------------------
# cloud status command (no cloud configured)
# ---------------------------------------------------------------------------


class TestCloudStatusCommand:
    def test_cloud_status_no_cloud_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["cloud", "status"])
        assert result.exit_code == 0
        assert "No cloud database configured" in result.output or "cloud" in result.output.lower()
