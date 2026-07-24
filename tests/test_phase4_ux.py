"""Phase 4 UX tests — dashboard, smart errors, next steps, typed confirmation, history."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def test_welcome_dashboard_outside_project(tmp_path, monkeypatch):
    """Welcome dashboard should print even when no .kaira.json exists."""
    monkeypatch.chdir(tmp_path)
    from kaira.commands.dashboard import welcome_dashboard
    with patch("kaira.commands.dashboard.console") as mock_console:
        welcome_dashboard()
        # Should have printed something (a panel or message)
        assert mock_console.print.called


def test_welcome_dashboard_inside_project(tmp_path, monkeypatch):
    """Welcome dashboard should show project details when .kaira.json exists."""
    monkeypatch.chdir(tmp_path)
    config = {
        "project_name": "TestProject",
        "db_type": "postgresql",
        "generated_models": [{"name": "User", "fields": []}],
        "output_dir": "src",
        "default_tier": "full",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(config))
    from kaira.commands.dashboard import welcome_dashboard
    with patch("kaira.commands.dashboard.console") as mock_console:
        welcome_dashboard()
        assert mock_console.print.called


# ---------------------------------------------------------------------------
# Next steps
# ---------------------------------------------------------------------------


def test_print_next_steps_empty(capsys):
    """print_next_steps with empty list should not print anything."""
    from kaira.commands.ux_helpers import print_next_steps
    with patch("kaira.commands.ux_helpers.console") as mock_console:
        print_next_steps([])
        mock_console.print.assert_not_called()


def test_print_next_steps_with_items():
    """print_next_steps should print a panel with provided steps."""
    from kaira.commands.ux_helpers import print_next_steps
    with patch("kaira.commands.ux_helpers.console") as mock_console:
        print_next_steps(["kaira migrate init", "kaira test generate User"])
        assert mock_console.print.called


# ---------------------------------------------------------------------------
# Typed confirmation
# ---------------------------------------------------------------------------


def test_typed_confirmation_correct_word(monkeypatch):
    """Typed confirmation should return True when user types the word correctly."""
    from kaira.commands.ux_helpers import typed_confirmation
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "production")
    result = typed_confirmation("production", "Deleting everything.")
    assert result is True


def test_typed_confirmation_wrong_word(monkeypatch):
    """Typed confirmation should return False when user types the wrong word."""
    from kaira.commands.ux_helpers import typed_confirmation
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "wrong")
    result = typed_confirmation("production", "Deleting everything.")
    assert result is False


def test_typed_confirmation_force_flag():
    """Typed confirmation with force=True should skip prompt and return True."""
    from kaira.commands.ux_helpers import typed_confirmation
    result = typed_confirmation("production", "Deleting everything.", force=True)
    assert result is True


# ---------------------------------------------------------------------------
# mask_credentials
# ---------------------------------------------------------------------------


def test_mask_credentials_url():
    """mask_credentials should replace password in a connection URL."""
    from kaira.commands.ux_helpers import mask_credentials
    url = "postgresql://user:supersecretpassword@localhost:5432/mydb"
    masked = mask_credentials(url)
    assert "supersecretpassword" not in masked
    assert "****" in masked or "***" in masked


def test_mask_credentials_no_password():
    """mask_credentials with no password should return url unchanged."""
    from kaira.commands.ux_helpers import mask_credentials
    url = "redis://localhost:6379"
    result = mask_credentials(url)
    assert "localhost" in result


# ---------------------------------------------------------------------------
# Fuzzy suggestions
# ---------------------------------------------------------------------------


def test_suggest_did_you_mean_close_match():
    """suggest_did_you_mean should return closest match for a typo."""
    from kaira.commands.ux_helpers import suggest_did_you_mean
    result = suggest_did_you_mean("generete", ["generate", "migrate", "init"])
    assert "generate" in result


def test_suggest_did_you_mean_no_match():
    """suggest_did_you_mean should return empty list when no close match exists."""
    from kaira.commands.ux_helpers import suggest_did_you_mean
    result = suggest_did_you_mean("zzzzz", ["generate", "migrate", "init"])
    assert result == []


# ---------------------------------------------------------------------------
# History redaction
# ---------------------------------------------------------------------------


def test_history_no_sensitive_data(tmp_path, monkeypatch):
    """Command history should never record passwords or tokens."""
    monkeypatch.chdir(tmp_path)
    from kaira.commands.ux_helpers import append_history
    # Attempt to record a command with a DB URL containing a password
    append_history("db connect", {"password": "s3cret"})
    history_file = tmp_path / ".kaira" / "history.jsonl"
    if history_file.exists():
        content = history_file.read_text()
        assert "s3cret" not in content


