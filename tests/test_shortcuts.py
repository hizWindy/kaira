"""Tests for Kaira command shortcuts, aliases, and shell completion."""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from kaira.core.aliases import (
    ALIASES,
    DESTRUCTIVE_COMMANDS,
    complete_guide_topic,
    complete_model_name,
    is_destructive_command,
    resolve_alias,
    resolve_argv,
)
from kaira.core.ui import _format_echo_tokens, render_resolution_echo
from kaira.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Section 7 Safety Tests
# ---------------------------------------------------------------------------


def test_no_shadowing():
    """No alias key equals any registered Typer command or group name."""
    registered_names: set[str] = set()
    for cmd in app.registered_commands:
        name = cmd.name or (cmd.callback.__name__ if cmd.callback else "")
        if name:
            registered_names.add(name)
    for grp in app.registered_groups:
        if grp.name:
            registered_names.add(grp.name)

    shadowed = set(ALIASES.keys()) & registered_names
    assert not shadowed, f"Alias keys shadow registered commands: {shadowed}"


def test_no_destructive_alias():
    """No alias resolves to any command on the destructive blocklist.

    The blocklist is a constant, checked by expansion, not by string matching the alias.
    """
    for alias, expansion in ALIASES.items():
        assert not is_destructive_command(expansion), (
            f"Alias '{alias}' resolves to destructive command: {expansion}"
        )
        for destructive in DESTRUCTIVE_COMMANDS:
            assert tuple(expansion[: len(destructive)]) != destructive, (
                f"Alias '{alias}' expands to destructive command: {expansion}"
            )


def test_no_dangling_alias():
    """Every alias expansion resolves to a command that exists in Typer app."""
    for alias, expansion in ALIASES.items():
        current = app
        for i, token in enumerate(expansion):
            matching_cmd = next(
                (
                    c
                    for c in current.registered_commands
                    if (c.name or (c.callback.__name__ if c.callback else "")) == token
                ),
                None,
            )
            if matching_cmd is not None:
                assert i == len(expansion) - 1, (
                    f"Intermediate token '{token}' in '{alias}' matched a leaf command"
                )
                break

            matching_grp = next(
                (g for g in current.registered_groups if g.name == token),
                None,
            )
            assert matching_grp is not None, (
                f"Token '{token}' in alias '{alias}' expansion {expansion} not found in Typer"
            )
            current = matching_grp.typer_instance
            assert current is not None


def test_no_duplicate_expansion():
    """No two aliases expand to the same command."""
    seen_expansions: dict[tuple[str, ...], str] = {}
    for alias, expansion in ALIASES.items():
        exp_tuple = tuple(expansion)
        assert exp_tuple not in seen_expansions, (
            f"Aliases '{alias}' and '{seen_expansions[exp_tuple]}' expand to the same command: {expansion}"
        )
        seen_expansions[exp_tuple] = alias


# ---------------------------------------------------------------------------
# Passthrough Fidelity & Non-Alias Tests
# ---------------------------------------------------------------------------


def test_passthrough_fidelity():
    """kaira g User --fields 'a:str' --tier full produces identical argv to long form."""
    raw_argv = ["kaira", "g", "User", "--fields", "a:str", "--tier", "full"]
    resolved, was_aliased = resolve_argv(raw_argv)
    assert was_aliased is True
    expected = [
        "kaira",
        "generate",
        "model",
        "User",
        "--fields",
        "a:str",
        "--tier",
        "full",
    ]
    assert resolved == expected

    # Subcommand aliases are NOT supported: kaira docker g must remain untouched
    docker_g = ["kaira", "docker", "g"]
    resolved_docker, was_docker_aliased = resolve_argv(docker_g)
    assert was_docker_aliased is False
    assert resolved_docker == docker_g


def test_non_alias_argv_untouched():
    """A typo (kaira genrate) leaves argv completely alone for the fuzzy suggester."""
    typo_argv = ["kaira", "genrate", "model", "User"]
    resolved, was_aliased = resolve_argv(typo_argv)
    assert was_aliased is False
    assert resolved == typo_argv


# ---------------------------------------------------------------------------
# Echo Suppression & Redaction Tests
# ---------------------------------------------------------------------------


def test_echo_suppression():
    """Resolution line is suppressed under --quiet and on non-TTY output."""
    with patch("kaira.core.ui.console.print") as mock_print:
        # Non-interactive / non-TTY output: suppressed
        with patch("kaira.core.theme.is_interactive", return_value=False):
            with patch("kaira.core.theme.is_quiet", return_value=False):
                render_resolution_echo(["generate", "model", "User"])
                mock_print.assert_not_called()

        # Under --quiet (flag in Theme): suppressed even if interactive
        with patch("kaira.core.theme.is_interactive", return_value=True):
            with patch("kaira.core.theme.is_quiet", return_value=True):
                render_resolution_echo(["generate", "model", "User"])
                mock_print.assert_not_called()

        # Under --quiet in arguments: suppressed
        with patch("kaira.core.theme.is_interactive", return_value=True):
            with patch("kaira.core.theme.is_quiet", return_value=False):
                render_resolution_echo(["generate", "model", "User", "--quiet"])
                mock_print.assert_not_called()

        # Interactive and not quiet: printed
        with patch("kaira.core.theme.is_interactive", return_value=True):
            with patch("kaira.core.theme.is_quiet", return_value=False):
                render_resolution_echo(["generate", "model", "User"])
                mock_print.assert_called_once()
                args, _ = mock_print.call_args
                printed_text = args[0]
                assert "kaira generate model User" in printed_text


def test_echo_redaction():
    """An aliased command carrying a sensitive key/token/password never prints the value."""
    tokens = [
        "db",
        "connect",
        "--password",
        "super_secret_pw",
        "--api-key=super_api_key",
        "--token",
        "jwt_secret_token",
        "--dsn=postgres://user:dbpass@localhost/db",
        "--normal-flag",
        "normal_value",
    ]
    formatted = _format_echo_tokens(tokens)
    line = " ".join(formatted)

    assert "super_secret_pw" not in line
    assert "super_api_key" not in line
    assert "jwt_secret_token" not in line
    assert "dbpass" not in line
    assert "[REDACTED]" in line
    assert "normal_value" in line


# ---------------------------------------------------------------------------
# History Normalization Test
# ---------------------------------------------------------------------------


def test_history_normalization(tmp_path, monkeypatch):
    """Aliased invocation writes the long form to .kaira/history.jsonl; recap shows long form."""
    monkeypatch.chdir(tmp_path)

    # Invoke 'st' alias
    result = runner.invoke(app, ["st"])
    assert result.exit_code == 0

    history_path = tmp_path / ".kaira" / "history.jsonl"
    assert history_path.exists(), "History file was not created"
    content = history_path.read_text(encoding="utf-8").strip()
    assert content, "History file is empty"

    last_record = json.loads(content.splitlines()[-1])
    assert last_record["command"] == "status", (
        f"Expected 'status', got '{last_record['command']}'"
    )

    # Verify 'kaira recap show' renders the normalized long-form command
    recap_result = runner.invoke(app, ["recap", "show"])
    assert recap_result.exit_code == 0
    assert "status" in recap_result.output
    # Must NOT record alias 'st'
    assert last_record["command"] != "st"


# ---------------------------------------------------------------------------
# Completion Safety Tests
# ---------------------------------------------------------------------------


def test_completion_safety(tmp_path, monkeypatch):
    """Model-name completion returns [] on missing/malformed .kaira.json and never raises."""
    monkeypatch.chdir(tmp_path)

    # 1. Missing config file
    assert complete_model_name() == []
    assert complete_model_name(incomplete="U") == []

    # 2. Corrupted JSON file
    (tmp_path / ".kaira.json").write_text("{corrupted-json-content", encoding="utf-8")
    assert complete_model_name() == []

    # 3. Invalid schema (generated_models is not a list)
    (tmp_path / ".kaira.json").write_text(
        json.dumps({"generated_models": "not-a-list"}), encoding="utf-8"
    )
    assert complete_model_name() == []

    # 4. Valid config file
    config_data = {
        "generated_models": [
            {"name": "User", "fields": []},
            {"name": "Post", "fields": []},
            {"name": "Comment", "fields": []},
        ]
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(config_data), encoding="utf-8")
    assert sorted(complete_model_name()) == ["Comment", "Post", "User"]
    assert complete_model_name(incomplete="u") == ["User"]
    assert complete_model_name(incomplete="po") == ["Post"]
    assert complete_model_name(incomplete="xyz") == []


def test_guide_topic_completion():
    """Guide-topic completion returns topics from registered list."""
    topics = complete_guide_topic()
    assert "init" in topics
    assert "generate" in topics
    assert "shortcuts" in topics

    filtered = complete_guide_topic(incomplete="short")
    assert filtered == ["shortcuts"]


# ---------------------------------------------------------------------------
# Confirmation Intact Test
# ---------------------------------------------------------------------------


def test_confirmation_intact(tmp_path, monkeypatch):
    """An aliased command reaching a typed-confirmation path still requires it."""
    monkeypatch.chdir(tmp_path)
    # Setup .kaira.json with a model User having 2 fields
    config = {
        "project_name": "TestProject",
        "output_dir": ".",
        "db_type": "sqlite",
        "generated_models": [
            {
                "name": "User",
                "fields": [
                    {"name": "name", "type": "str"},
                    {"name": "old_field", "type": "str"},
                ],
            }
        ],
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")

    # Create dummy model file with only 1 field (old_field removed)
    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "user.py").write_text(
        "from pydantic import BaseModel\nclass User(BaseModel):\n    name: str\n",
        encoding="utf-8",
    )

    # When user enters wrong confirmation word, sync should abort
    monkeypatch.setattr("typer.prompt", lambda *a, **kw: "wrong")
    result = runner.invoke(app, ["sm", "User"])
    assert "Aborted" in result.output or "aborted" in result.output.lower()


# ---------------------------------------------------------------------------
# Discoverability Tests
# ---------------------------------------------------------------------------


def test_commands_shortcuts_block():
    """kaira commands renders the Shortcuts block via data_table()."""
    result = runner.invoke(app, ["commands"])
    assert result.exit_code == 0
    assert "Shortcuts" in result.output
    assert "generate model" in result.output
    assert "docker up" in result.output
    assert "Shortcuts are optional. Full commands always work." in result.output
    assert "Tab-completion: kaira --install-completion" in result.output


def test_guide_shortcuts_page():
    """kaira guide shortcuts renders the guide panel and notes safety exclusions."""
    result = runner.invoke(app, ["guide", "shortcuts"])
    assert result.exit_code == 0
    assert "⚡ Kaira — Guide: shortcuts" in result.output
    assert "No destructive command has an alias" in result.output
    assert "kaira '?'" in result.output

    # Check guide index
    index_result = runner.invoke(app, ["guide"])
    assert index_result.exit_code == 0
    assert "kaira guide shortcuts" in index_result.output


# ---------------------------------------------------------------------------
# Core Aliases Helper Edge Cases
# ---------------------------------------------------------------------------


def test_core_aliases_helpers():
    """Test resolve_alias, is_destructive_command, and tokens_to_args_dict."""
    from kaira.core.aliases import tokens_to_args_dict

    # resolve_alias unknown
    assert resolve_alias("nonexistent") is None

    # is_destructive_command positive and negative
    assert is_destructive_command(["db", "reset"]) is True
    assert is_destructive_command(["db", "reset", "--extra"]) is True
    assert is_destructive_command(["migrate", "rollback"]) is True
    assert is_destructive_command(["status"]) is False

    # tokens_to_args_dict variations
    d1 = tokens_to_args_dict(["generate", "bulk"], ["my_models.json", "--force"])
    assert d1 == {"file": "my_models.json", "force": "true"}

    d2 = tokens_to_args_dict(
        ["migrate", "make"], ["add_field", "--tier=full", "-m", "msg"]
    )
    assert d2 == {"message": "add_field", "tier": "full", "m": "msg"}

    d3 = tokens_to_args_dict(["test", "run"], ["-v"])
    assert d3 == {"v": "true"}


def test_completion_callbacks_exception_handling():
    """Completion callbacks catch unexpected exceptions and return [] silently."""
    with patch("pathlib.Path.cwd", side_effect=RuntimeError("disk failure")):
        assert complete_model_name() == []

    with patch(
        "kaira.core.aliases.GUIDE_TOPICS", side_effect=RuntimeError("corrupt list")
    ):
        assert complete_guide_topic() == []
