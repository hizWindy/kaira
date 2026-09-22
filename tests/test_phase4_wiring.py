"""Phase 4 wiring tests — verifies that all new command groups and commands are correctly registered in main.py."""

from __future__ import annotations

from typer.testing import CliRunner

from kaira.main import app


def test_wiring_registration():
    """Verify that all Phase 4 commands and subcommand groups are registered in kaira.main.app."""
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0

    # Check that subcommand groups are listed in help text
    output = result.output.lower()
    expected_subcommands = [
        "status",
        "recap",
        "db",
        "deps",
        "quality",
        "cache",
        "task",
        "integrate",
        "api",
        "profile",
        "loadtest",
        "deploy",
        "middleware",
        "event",
        "notify",
        "flags",
        "health-endpoint",
    ]
    for cmd in expected_subcommands:
        assert cmd in output
