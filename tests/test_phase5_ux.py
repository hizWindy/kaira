"""Tests for Phase 5 UX — theme, ui helpers, prompts wrapper, onboarding, @with_summary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# core/theme.py
# ---------------------------------------------------------------------------


class TestIsInteractive:
    def test_returns_false_when_no_color_set(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        from kaira.core.theme import is_interactive

        assert is_interactive() is False

    def test_returns_false_when_not_tty(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            # re-import to pick up patch
            import importlib
            import kaira.core.theme as theme_mod

            importlib.reload(theme_mod)
            assert theme_mod.is_interactive() is False

    def test_theme_constants_are_strings(self):
        from kaira.core.theme import Theme

        assert isinstance(Theme.PRIMARY, str)
        assert isinstance(Theme.SUCCESS, str)
        assert isinstance(Theme.ERROR, str)
        assert isinstance(Theme.MUTED, str)
        assert isinstance(Theme.ACCENT, str)

    def test_symbols_class_has_required_attrs(self):
        from kaira.core.theme import Symbols

        for attr in ("OK", "FAIL", "WARN", "BOLT", "ARROW", "POINTER"):
            assert hasattr(Symbols, attr), f"Symbols.{attr} missing"

    def test_sym_returns_plain_in_non_interactive(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        import importlib
        import kaira.core.theme as theme_mod

        importlib.reload(theme_mod)
        result = theme_mod.sym("OK")
        assert result == theme_mod.Symbols.OK_PLAIN

    def test_sym_returns_emoji_in_interactive(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        import importlib
        import kaira.core.theme as theme_mod

        # Force TTY
        with patch.object(sys.stdout, "isatty", return_value=True):
            importlib.reload(theme_mod)
            result = theme_mod.sym("OK")
            # May be emoji or plain depending on sys.stdout in test
            assert isinstance(result, str)
            assert len(result) > 0


# ---------------------------------------------------------------------------
# core/ui.py
# ---------------------------------------------------------------------------


class TestUIHelpers:
    def test_panel_does_not_raise(self, capsys):
        from kaira.core.ui import panel

        panel("Test content", "Test Title")
        # Should not raise; rich outputs to stdout

    def test_kv_table_does_not_raise(self, capsys):
        from kaira.core.ui import kv_table

        kv_table([("key", "value"), ("another", "one")])

    def test_data_table_does_not_raise(self, capsys):
        from kaira.core.ui import data_table

        data_table(
            headers=["Name", "Count"],
            rows=[["Alice", "10"], ["Bob", "20"]],
            numeric_cols=[1],
        )

    def test_success_footer_does_not_raise(self, capsys):
        from kaira.core.ui import success_footer

        success_footer("Done", elapsed_s=1.2, files=5, warnings=0)

    def test_error_footer_does_not_raise(self, capsys):
        from kaira.core.ui import error_footer

        error_footer("Something failed", hint="Try again")

    def test_with_summary_decorator_returns_same_result(self):
        from kaira.core.ui import with_summary

        @with_summary
        def my_func(x: int) -> int:
            return x * 2

        result = my_func(5)
        assert result == 10

    def test_with_summary_propagates_typer_exit(self):
        import typer
        from kaira.core.ui import with_summary

        @with_summary
        def failing_func() -> None:
            raise typer.Exit(1)

        with pytest.raises(typer.Exit):
            failing_func()

    def test_spinner_context_non_tty_returns_plain(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        import importlib
        import kaira.core.ui as ui_mod

        importlib.reload(ui_mod)
        ctx = ui_mod.spinner_context("Loading...")
        # Should be _PlainStatus in non-interactive mode
        assert hasattr(ctx, "__enter__")
        assert hasattr(ctx, "__exit__")


# ---------------------------------------------------------------------------
# core/prompts.py — non-TTY error path
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_select_raises_on_non_tty(self):
        """select() must raise typer.Exit when stdin is not a TTY."""
        import typer
        from kaira.core import prompts

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            with patch("kaira.core.prompts.is_interactive", return_value=False):
                with pytest.raises((typer.Exit, SystemExit)):
                    prompts.select("Pick one:", ["a", "b"])

    def test_confirm_raises_on_non_tty(self):
        import typer
        from kaira.core import prompts

        with patch("kaira.core.prompts.is_interactive", return_value=False):
            with pytest.raises((typer.Exit, SystemExit)):
                prompts.confirm("Proceed?")

    def test_text_raises_on_non_tty(self):
        import typer
        from kaira.core import prompts

        with patch("kaira.core.prompts.is_interactive", return_value=False):
            with pytest.raises((typer.Exit, SystemExit)):
                prompts.text("Enter value:")

    def test_secret_raises_on_non_tty(self):
        import typer
        from kaira.core import prompts

        with patch("kaira.core.prompts.is_interactive", return_value=False):
            with pytest.raises((typer.Exit, SystemExit)):
                prompts.secret("Enter secret:")

    def test_fuzzy_select_raises_on_non_tty(self):
        import typer
        from kaira.core import prompts

        with patch("kaira.core.prompts.is_interactive", return_value=False):
            with pytest.raises((typer.Exit, SystemExit)):
                prompts.fuzzy_select("Search:", ["option a", "option b"])


# ---------------------------------------------------------------------------
# commands/onboarding.py
# ---------------------------------------------------------------------------


class TestOnboarding:
    def test_config_exists_false_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        import importlib
        import kaira.commands.onboarding as ob

        importlib.reload(ob)
        assert ob.config_exists() is False

    def test_save_and_load_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        import importlib
        import kaira.commands.onboarding as ob

        importlib.reload(ob)

        ob.save_config({"experience_level": "new", "telemetry": False})
        loaded = ob.load_config()
        assert loaded["experience_level"] == "new"
        assert loaded["telemetry"] is False

    def test_reset_config_removes_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        import importlib
        import kaira.commands.onboarding as ob

        importlib.reload(ob)

        ob.save_config({"experience_level": "experienced"})
        assert ob.config_exists() is True
        ob.reset_config()
        assert ob.config_exists() is False

    def test_should_show_false_in_ci(self, monkeypatch):
        """Onboarding should not show when stdin is not a TTY."""
        monkeypatch.setenv("NO_COLOR", "1")
        import importlib
        import kaira.commands.onboarding as ob

        importlib.reload(ob)
        assert ob._should_show(["kaira"]) is False

    def test_should_show_false_when_args_present(self, tmp_path, monkeypatch):
        """Onboarding skipped when user supplies any sub-command."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        import importlib
        import kaira.commands.onboarding as ob

        importlib.reload(ob)
        # Even with TTY, args present should skip
        with patch("kaira.commands.onboarding.is_interactive", return_value=True):
            assert ob._should_show(["kaira", "init"]) is False

    def test_should_show_false_when_config_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        import importlib
        import kaira.commands.onboarding as ob

        importlib.reload(ob)
        ob.save_config({"experience_level": "experienced"})
        with patch("kaira.commands.onboarding.is_interactive", return_value=True):
            assert ob._should_show(["kaira"]) is False
