"""Tests for Phase 7.5 — Banner, Progress UI & Command Index.

Covers:
- FEATURE A: banner lockup alignment and three-tier degradation
- FEATURE A: banner on the entry-point surfaces, absent on working commands
- FEATURE B: phase/item model, live layout, truncation, collapse & failure
- FEATURE B: batched uv-first installer, parsed item states, error mapping
- FEATURE C: kaira commands index, --group, --search, and the drift test
- GUIDE: kaira guide commands
- Non-regression: exit codes and side effects of the retrofitted commands
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
import typer
from typer.testing import CliRunner

from kaira.commands import project as project_mod
from kaira.commands.commands_cmd import introspect_typer_app
from kaira.commands.deps_cmd import _parse_dependency_array
from kaira.commands.project import (
    _InstallOutputParser,
    classify_install_error,
    install_packages,
)
from kaira.core.progress import (
    MAX_VISIBLE_ROWS,
    state_symbol,
    ProgressItem,
    ProgressPhase,
    ProgressRenderer,
    State,
    create_install_renderer,
)
from kaira.core import ui
from kaira.core.theme import GUTTER, RULE_WIDTH, get_banner
from kaira.main import app

runner = CliRunner()

_MARKUP_RE = re.compile(r"\[/?[a-z0-9 #_]+\]", re.IGNORECASE)


def strip_markup(text: str) -> str:
    """Drop Rich style tags so assertions read the rendered text."""
    return _MARKUP_RE.sub("", text)


@pytest.fixture()
def tty(monkeypatch):
    """Present an interactive, colour, UTF-8, 80-column terminal."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: True)
    monkeypatch.setattr("kaira.core.theme.terminal_width", lambda: 80)
    monkeypatch.delenv("NO_COLOR", raising=False)


# ---------------------------------------------------------------------------
# FEATURE A: Banner & three-tier degradation
# ---------------------------------------------------------------------------


class TestBanner:
    def test_full_banner_tier1(self, tty):
        """Interactive TTY + UTF-8 + colour produces the wordmark with flanks."""
        banner = get_banner("1.0.0")
        assert "⚙️" in banner
        assert "⚡" in banner
        assert "v1.0.0" in banner
        assert "continuous scaffolding" in banner

    def test_wordmark_lines_share_a_left_edge(self, tty):
        """The two wordmark lines and the tagline align on the same column.

        Line 2 is prefixed by the gear, which occupies exactly the columns the
        other lines indent by.  A mismatch here is what makes the banner look
        broken in real terminals.
        """
        line1, line2, tagline = strip_markup(get_banner("1.0.0")).splitlines()

        indent = len(line1) - len(line1.lstrip())
        assert indent == len(tagline) - len(tagline.lstrip())
        # The gear + space stands in for the indent on line 2.
        assert line2.startswith("⚙️ ")
        assert len(line2.split(" ", 1)[0]) + 1 == indent

    def test_wordmark_lines_are_equal_width(self, tty):
        """Both halves of the block wordmark are the same width."""
        line1, line2, _ = strip_markup(get_banner("1.0.0")).splitlines()
        top = line1.strip()
        # Strip the gear prefix and bolt suffix from line 2.
        bottom = line2.split(" ", 1)[1].rsplit(" ", 1)[0]
        assert len(top) == len(bottom)

    def test_nocolor_banner_tier2(self, tty, monkeypatch):
        """NO_COLOR keeps the wordmark and flanks but emits no markup."""
        monkeypatch.setenv("NO_COLOR", "1")
        banner = get_banner("1.0.0")
        assert "⚙️" in banner
        assert "⚡" in banner
        assert "[" not in banner

    def test_nocolor_banner_stays_aligned(self, tty, monkeypatch):
        """Tier 2 keeps the shared left edge as well."""
        monkeypatch.setenv("NO_COLOR", "1")
        line1, line2, tagline = get_banner("1.0.0").splitlines()
        assert len(line1) - len(line1.lstrip()) == len(tagline) - len(tagline.lstrip())
        assert line2.startswith("⚙️ ")

    def test_plain_banner_tier3_non_tty(self, tty, monkeypatch):
        """Non-TTY stdout collapses to the single plain line."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        assert get_banner("1.0.0") == (
            "KAIRA v1.0.0 · continuous model-level FastAPI scaffolding"
        )

    def test_plain_banner_tier3_non_utf8(self, tty, monkeypatch):
        """A non-UTF-8 console collapses to the single plain line."""
        monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: False)
        assert get_banner("1.0.0").startswith("KAIRA v1.0.0")

    def test_plain_banner_tier3_narrow(self, tty, monkeypatch):
        """A terminal under 32 columns collapses to the single plain line."""
        monkeypatch.setattr("kaira.core.theme.terminal_width", lambda: 28)
        assert get_banner("1.0.0").startswith("KAIRA v1.0.0")

    @pytest.mark.parametrize(
        "argv", [["about"], ["--version"], ["commands"], ["--help"], []]
    )
    def test_banner_on_entrypoints(self, argv):
        """Entry-point surfaces render the banner."""
        result = runner.invoke(app, argv)
        assert "KAIRA" in result.output or "continuous scaffolding" in result.output

    @pytest.mark.parametrize("argv", [["check"], ["info"], ["list", "--help"]])
    def test_banner_absent_on_working_commands(self, argv):
        """Working commands never render the banner."""
        result = runner.invoke(app, argv)
        assert "KAIRA v" not in result.output
        assert "continuous scaffolding" not in result.output


# ---------------------------------------------------------------------------
# FEATURE B: Phase/item model
# ---------------------------------------------------------------------------


class TestProgressModel:
    def test_state_enum_values(self):
        """The five documented states exist with their documented values."""
        assert [s.value for s in State] == [
            "pending",
            "active",
            "done",
            "partial",
            "failed",
        ]

    def test_item_lifecycle(self):
        """An item moves PENDING → ACTIVE → DONE and records a version."""
        item = ProgressItem(name="fastapi")
        assert item.state == State.PENDING
        item.start()
        assert item.state == State.ACTIVE
        item.done(version="0.115.0")
        assert item.state == State.DONE
        assert item.version == "0.115.0"

    def test_phase_finish_derives_state_from_items(self):
        """A phase resolves to DONE / PARTIAL / FAILED based on its items."""
        ok = ProgressPhase(name="install", items=[ProgressItem("a", State.DONE)])
        ok.finish()
        assert ok.state == State.DONE

        mixed = ProgressPhase(
            name="install",
            items=[ProgressItem("a", State.DONE), ProgressItem("b", State.FAILED)],
        )
        mixed.finish()
        assert mixed.state == State.PARTIAL

        broken = ProgressPhase(name="install", items=[ProgressItem("a", State.FAILED)])
        broken.finish()
        assert broken.state == State.FAILED

    def test_ascii_fallback_symbols(self, monkeypatch):
        """Symbols degrade to ASCII when the terminal is not interactive."""
        monkeypatch.setattr("kaira.core.theme.is_interactive", lambda: False)
        from kaira.core.progress import state_symbol

        assert state_symbol(State.PENDING) == "."
        assert state_symbol(State.ACTIVE) == ">"
        assert state_symbol(State.DONE) == "[ok]"
        assert state_symbol(State.PARTIAL) == "[!]"
        assert state_symbol(State.FAILED) == "[x]"


# ---------------------------------------------------------------------------
# FEATURE B: Live layout
# ---------------------------------------------------------------------------


class TestLiveLayout:
    def _install_renderer(self, count=12):
        packages = [f"pkg{i}" for i in range(count)]
        return create_install_renderer(packages, "uv")

    def test_all_phases_visible_from_the_start(self):
        """The whole job shape is visible before anything has run."""
        renderer, resolve, _, _ = self._install_renderer()
        resolve.start()
        live = strip_markup(renderer.render_live())
        assert "resolve" in live and "download" in live and "install" in live
        # Pending phases carry the pending symbol, not a blank line.
        pending = state_symbol(State.PENDING)
        assert f"{pending} download" in live and f"{pending} install" in live

    def test_nested_items_only_under_the_active_phase(self):
        """Items appear under the active phase and nowhere else."""
        renderer, resolve, download, install = self._install_renderer()
        resolve.start()
        assert "pkg0" not in strip_markup(renderer.render_live())

        resolve.finish()
        download.finish()
        install.start()
        assert "pkg0" in strip_markup(renderer.render_live())

    def test_nested_list_truncates_to_a_fixed_height(self):
        """The nested block stays MAX_VISIBLE_ROWS tall regardless of size."""
        renderer, resolve, download, install = self._install_renderer(count=40)
        resolve.finish()
        download.finish()
        install.start()

        live = strip_markup(renderer.render_live()).splitlines()
        nested = [line for line in live if line.startswith(GUTTER + "  ")]
        assert len(nested) == MAX_VISIBLE_ROWS
        assert nested[-1].strip().endswith("more")

    def test_truncation_keeps_the_frontier_visible(self):
        """Active and recently-resolved items stay on screen; pending folds."""
        renderer, resolve, download, install = self._install_renderer(count=12)
        resolve.finish()
        download.finish()
        install.start()
        for item in install.items[:7]:
            item.done()
        install.items[7].start()

        live = strip_markup(renderer.render_live())
        assert "pkg7" in live  # active
        assert "pkg6" in live  # most recently completed
        assert "pkg0" not in live  # long done, folded away
        assert "+" in live and "more" in live

    def test_collapse_on_success_keeps_phase_timings(self):
        """Full success drops nested detail but keeps the per-phase timings."""
        renderer, resolve, download, install = self._install_renderer(count=3)
        resolve.start()
        resolve.finish("3 packages")
        resolve.elapsed_s = 0.34
        download.start()
        download.finish("18.2 MB")
        download.elapsed_s = 2.1
        install.start()
        for item in install.items:
            item.done(version="1.0.0")
        install.finish("3 packages")
        install.elapsed_s = 5.9

        summary = strip_markup(renderer.render_summary())
        assert "340ms" in summary and "2.1s" in summary and "5.9s" in summary
        assert "ready" in summary
        assert "pkg0" not in summary  # nested detail collapsed

    def test_failure_expands_only_the_failing_phase(self):
        """Successful phases stay collapsed; only failed items are listed."""
        renderer, resolve, download, install = self._install_renderer(count=3)
        resolve.finish("3 packages")
        download.finish("18.2 MB")
        install.start()
        install.items[0].done(version="1.0.0")
        install.items[1].done(version="2.0.0")
        install.items[2].fail("missing postgresql headers")
        install.finish("2 ok · 1 failed")

        out = strip_markup(
            renderer.render_failure(
                ["sudo apt install libpq-dev", "kaira deps add pkg2"]
            )
        )
        assert "pkg2" in out and "missing postgresql headers" in out
        assert "pkg0" not in out and "pkg1" not in out
        assert "sudo apt install libpq-dev" in out
        assert "kaira deps add pkg2" in out

    def test_progress_bar_tracks_resolved_items(self):
        """The bar counts resolved items against the operation total."""
        renderer, resolve, download, install = self._install_renderer(count=4)
        resolve.finish()
        download.finish()
        install.start()
        install.items[0].done()
        assert "1/4" in strip_markup(renderer.render_live())


# ---------------------------------------------------------------------------
# FEATURE B: Non-interactive / CI path
# ---------------------------------------------------------------------------


class TestPlainPath:
    def test_plain_output_has_no_control_codes(self, monkeypatch, capsys):
        """CI output carries no ANSI, no cursor moves, and no spinner frames."""
        monkeypatch.setattr("kaira.core.progress.is_interactive", lambda: False)
        phase = ProgressPhase(name="install", items=[ProgressItem("fastapi")])
        renderer = ProgressRenderer(
            "installing", strategy="pip", total=1, phases=[phase]
        )

        renderer.start()
        phase.start()
        renderer.refresh()
        phase.items[0].done(version="0.115.0")
        phase.finish("1 packages")
        renderer.refresh()
        renderer.print_result()

        out = capsys.readouterr().out
        assert "\x1b[" not in out
        assert "◐" not in out and "◌" not in out
        assert "[ok] install" in out
        assert "ready in" in out

    def test_plain_emits_one_line_per_phase_as_it_resolves(self, monkeypatch, capsys):
        """Each phase prints exactly once, when it resolves."""
        monkeypatch.setattr("kaira.core.progress.is_interactive", lambda: False)
        renderer, resolve, download, install = create_install_renderer(["a"], "pip")

        renderer.start()
        resolve.start()
        renderer.refresh()
        assert "resolve" not in capsys.readouterr().out

        resolve.finish("1 packages")
        renderer.refresh()
        renderer.refresh()  # a second refresh must not duplicate the line
        out = capsys.readouterr().out
        assert out.count("resolve") == 1

    def test_plain_failure_lists_reason_and_hints(self, monkeypatch, capsys):
        """Failures print the short reason and the fix commands in CI too."""
        monkeypatch.setattr("kaira.core.progress.is_interactive", lambda: False)
        renderer, resolve, download, install = create_install_renderer(
            ["asyncpg"], "pip"
        )
        resolve.finish()
        download.finish()
        install.start()
        install.items[0].fail("missing postgresql headers")
        install.finish("0 ok · 1 failed")
        renderer.refresh()
        renderer.print_result(["sudo apt install libpq-dev"])

        out = capsys.readouterr().out
        assert "missing postgresql headers" in out
        assert "sudo apt install libpq-dev" in out


# ---------------------------------------------------------------------------
# FEATURE B: Installer strategy and output parsing
# ---------------------------------------------------------------------------


class _FakeProc:
    """Minimal stand-in for a streamed subprocess."""

    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(lines)
        self._returncode = returncode

    def wait(self) -> int:
        """Return the recorded exit status."""
        return self._returncode


@pytest.fixture()
def fake_installer(monkeypatch):
    """Capture the installer command line and script its output."""
    calls: list[list[str]] = []
    script: dict[str, object] = {"lines": [], "returncode": 0}

    monkeypatch.setattr("kaira.config.get_venv_python", lambda *a, **k: sys.executable)

    def fake_popen(cmd, **kwargs):
        calls.append(list(cmd))
        return _FakeProc(list(script["lines"]), int(script["returncode"]))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    return calls, script


class TestInstaller:
    def test_uv_is_preferred_and_the_batch_is_one_invocation(
        self, fake_installer, monkeypatch
    ):
        """uv wins when present, and every package goes in one command."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: "/usr/bin/uv")
        script["lines"] = [
            "Resolved 2 packages in 340ms\n",
            "Prepared 2 packages in 1.2s\n",
            "Installed 2 packages in 900ms\n",
            " + kaira-fake-a==1.0.0\n",
            " + kaira-fake-b==2.0.0\n",
        ]

        installed, failed, _ = install_packages(["kaira-fake-a", "kaira-fake-b"])

        assert len(calls) == 1, "packages must not be installed one at a time"
        assert calls[0][0] == "/usr/bin/uv"
        assert "kaira-fake-a" in calls[0] and "kaira-fake-b" in calls[0]
        assert (installed, failed) == (2, 0)

    def test_pip_fallback_is_silent_and_batched(
        self, fake_installer, monkeypatch, capsys
    ):
        """Without uv the run falls back to pip with no nag, still batched."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: None)
        script["lines"] = [
            "Collecting kaira-fake-a\n",
            "  Downloading kaira_fake_a-1.0.0-py3-none-any.whl (18.2 MB)\n",
            "Installing collected packages: kaira-fake-a, kaira-fake-b\n",
            "Successfully installed kaira-fake-a-1.0.0 kaira-fake-b-2.0.0\n",
        ]

        install_packages(["kaira-fake-a", "kaira-fake-b"])

        assert len(calls) == 1
        assert calls[0][:3] == [sys.executable, "-m", "pip"]
        out = capsys.readouterr().out.lower()
        assert "uv" not in out.replace("install", "")  # no "install uv" nag

    def test_upgrade_passes_the_flag_once_for_the_whole_set(
        self, fake_installer, monkeypatch
    ):
        """deps update upgrades the full set in a single resolver run."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: None)
        script["lines"] = ["Successfully installed kaira-fake-a-1.0.0\n"]

        install_packages(["kaira-fake-a", "kaira-fake-b"], upgrade=True)

        assert len(calls) == 1
        assert calls[0].count("--upgrade") == 1

    def test_raw_installer_output_is_never_rendered(
        self, fake_installer, monkeypatch, capsys
    ):
        """Stack traces and index URLs stay out of the terminal."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: None)
        script["returncode"] = 1
        script["lines"] = [
            "Looking in indexes: https://user:s3cr3t@pypi.example.com/simple\n",
            "  error: subprocess-exited-with-error\n",
            "  Traceback (most recent call last):\n",
            "  pg_config executable not found.\n",
        ]

        installed, failed, _ = install_packages(["kaira-fake-asyncpg"])

        out = capsys.readouterr().out
        assert "s3cr3t" not in out
        assert "pypi.example.com" not in out
        assert "Traceback" not in out
        assert "subprocess-exited-with-error" not in out
        assert "missing postgresql headers" in out
        assert "sudo apt install libpq-dev" in out
        assert (installed, failed) == (0, 1)

    def test_unknown_failure_gets_a_generic_reason_not_a_dump(
        self, fake_installer, monkeypatch, capsys
    ):
        """An unparseable failure still never dumps raw output."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: None)
        script["returncode"] = 1
        script["lines"] = ["something nobody has ever seen before\n"]

        install_packages(["kaira-fake-zzz"])

        out = capsys.readouterr().out
        assert "something nobody has ever seen" not in out
        assert "install failed" in out
        assert "kaira deps add kaira-fake-zzz" in out

    def test_failure_before_install_isolates_to_its_phase(
        self, fake_installer, monkeypatch, capsys
    ):
        """A resolution failure marks resolve, and install never expands."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: None)
        script["returncode"] = 1
        script["lines"] = [
            "ERROR: No matching distribution found for kaira-fake-zzz\n",
        ]

        install_packages(["kaira-fake-zzz"])

        out = capsys.readouterr().out
        assert "no matching distribution" in out
        assert "[x] resolve" in out
        assert "[x] install" not in out


class TestInstallOutputParser:
    def _parser(self, packages):
        renderer, resolve, download, install = create_install_renderer(packages, "uv")
        parser = _InstallOutputParser("uv", resolve, download, install)
        resolve.start()
        return parser, resolve, download, install

    def test_uv_markers_drive_phase_transitions(self):
        """Phases advance on the installer's own statements, not on timers."""
        parser, resolve, download, install = self._parser(["fastapi"])

        parser.feed("Resolved 1 package in 340ms\n")
        assert resolve.state == State.DONE and download.state == State.ACTIVE

        parser.feed("Prepared 1 package in 1.2s\n")
        assert download.state == State.DONE and install.state == State.ACTIVE

        parser.feed(" + fastapi==0.115.0\n")
        assert install.items[0].state == State.DONE
        assert install.items[0].version == "0.115.0"

    def test_pip_markers_drive_phase_transitions(self):
        """The pip path resolves items only from 'Successfully installed'."""
        parser, resolve, download, install = self._parser(["fastapi", "pydantic"])

        parser.feed("Collecting fastapi\n")
        assert resolve.state == State.ACTIVE

        parser.feed("  Downloading fastapi-0.115.0-py3-none-any.whl (18.2 MB)\n")
        assert resolve.state == State.DONE and download.state == State.ACTIVE

        parser.feed("Installing collected packages: fastapi, pydantic\n")
        assert install.state == State.ACTIVE
        # Nothing is guessed mid-flight: pip reports no per-package completion.
        assert all(i.state == State.PENDING for i in install.items)

        parser.feed("Successfully installed fastapi-0.115.0 pydantic-2.10.0\n")
        assert [i.state for i in install.items] == [State.DONE, State.DONE]
        assert install.items[1].version == "2.10.0"

    def test_never_more_than_one_active_item_on_the_pip_path(self):
        """The pip path never fakes parallelism."""
        parser, resolve, download, install = self._parser(["a", "b", "c"])
        for line in (
            "Collecting a\n",
            "  Downloading a-1.0.tar.gz (1.0 MB)\n",
            "Collecting b\n",
            "  Downloading b-1.0.tar.gz (1.0 MB)\n",
            "Installing collected packages: a, b, c\n",
        ):
            parser.feed(line)
        active = [i for i in install.items if i.state == State.ACTIVE]
        assert len(active) <= 1

    def test_download_size_is_accumulated(self):
        """Reported sizes roll up into the download phase summary."""
        parser, resolve, download, install = self._parser(["a"])
        parser.feed("  Downloading a-1.0-py3-none-any.whl (10.0 MB)\n")
        parser.feed("  Downloading b-1.0-py3-none-any.whl (8.2 MB)\n")
        parser.feed("Installing collected packages: a\n")
        assert "MB" in download.summary

    def test_finalize_marks_the_running_phase_as_the_failure(self):
        """On failure the phase still running is the one that broke."""
        parser, resolve, download, install = self._parser(["a"])
        parser.finalize(success=False)
        assert resolve.state == State.FAILED
        assert download.state == State.PENDING
        assert install.state == State.PENDING


class TestErrorClassification:
    @pytest.mark.parametrize(
        "output,reason,hint",
        [
            (
                "pg_config executable not found",
                "missing postgresql headers",
                "libpq-dev",
            ),
            (
                "fatal error: Python.h: No such file",
                "missing python headers",
                "python3-dev",
            ),
            (
                "error: Microsoft Visual C++ 14.0 or greater is required",
                "missing c++ build tools",
                "Build Tools",
            ),
            (
                "ERROR: No matching distribution found for nope",
                "no matching distribution",
                "kaira deps add",
            ),
            ("ResolutionImpossible: ...", "dependency conflict", "kaira deps add"),
            ("OSError: [Errno 28] No space left on device", "no disk space left", ""),
            ("Temporary failure in name resolution", "network unreachable", ""),
            ("PermissionError: [Errno 13] Permission denied", "permission denied", ""),
        ],
    )
    def test_known_cases_map_to_short_reasons(self, output, reason, hint):
        """Known signatures become a short reason plus a fix command."""
        mapped, hints = classify_install_error(output, ["asyncpg"])
        assert mapped == reason
        if hint:
            assert any(hint in h for h in hints)

    def test_unknown_case_is_generic_with_a_hint(self):
        """Anything unrecognised gets the generic reason, never a dump."""
        raw = "https://user:token@index.internal/simple\nwild unparseable text"
        reason, hints = classify_install_error(raw, ["asyncpg"])
        assert reason == "install failed"
        assert hints == ["kaira deps add asyncpg"]
        assert "token" not in reason
        assert all("token" not in h for h in hints)


# ---------------------------------------------------------------------------
# FEATURE C: Command index
# ---------------------------------------------------------------------------


class TestCommandIndex:
    def test_index_is_grouped(self):
        """The index renders categories, not a flat list."""
        result = runner.invoke(app, ["commands"])
        assert result.exit_code == 0
        assert "SCAFFOLDING" in result.output
        assert "DATABASE" in result.output

    def test_group_filter(self):
        """--group narrows the output to one category."""
        result = runner.invoke(app, ["commands", "--group", "db"])
        assert result.exit_code == 0
        assert "DATABASE" in result.output
        assert "SCAFFOLDING" not in result.output

    def test_search_filter(self):
        """--search matches across names and descriptions."""
        result = runner.invoke(app, ["commands", "--search", "export"])
        assert result.exit_code == 0
        assert "export" in result.output.lower()

    def test_search_with_no_match_is_graceful(self):
        """An empty result set reports rather than rendering an empty index."""
        result = runner.invoke(app, ["commands", "--search", "zzzznotacommand"])
        assert result.exit_code == 0
        assert "No commands matched" in result.output

    def test_every_registered_command_appears_in_the_output(self, monkeypatch):
        """Drift test: the rendered index covers the whole registered app.

        A command added to the Typer tree without a category mapping must still
        show up — silently hiding commands defeats the point of the index.
        """
        monkeypatch.setenv("COLUMNS", "240")
        result = runner.invoke(app, ["commands"])
        assert result.exit_code == 0

        registered = {name for name, _help, _cat in introspect_typer_app(app)}
        assert registered, "introspection found no commands"

        missing = [name for name in registered if name not in result.output]
        assert not missing, f"missing from `kaira commands`: {sorted(missing)}"

    def test_commands_without_help_are_shown_not_hidden(self):
        """A command with no help text is listed with a muted placeholder."""
        sub = typer.Typer()

        @sub.command("undocumented")
        def _undocumented() -> None:
            pass

        entries = dict(
            (name, help_text) for name, help_text, _cat in introspect_typer_app(sub)
        )
        assert entries["undocumented"] == "(no description)"

    def test_index_is_read_only(self, monkeypatch):
        """The index executes nothing — no subprocess may be spawned."""

        def explode(*args, **kwargs):
            raise AssertionError("kaira commands must not execute anything")

        monkeypatch.setattr(subprocess, "run", explode)
        monkeypatch.setattr(subprocess, "Popen", explode)
        assert runner.invoke(app, ["commands"]).exit_code == 0


# ---------------------------------------------------------------------------
# Bare `kaira` — banner + dashboard
# ---------------------------------------------------------------------------


class TestWelcomeDashboard:
    def _project(self, tmp_path, monkeypatch, **overrides):
        """Write a minimal .kaira.json and chdir into it."""
        config = {
            "db_type": "sqlite",
            "auth_type": "jwt",
            "api_version": "v1",
            "db_name": "demo",
            "db_mode": "online",
            "output_dir": ".",
            "models_dir": "models",
            "routers_dir": "routers",
        }
        config.update(overrides)
        (tmp_path / ".kaira.json").write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_bare_kaira_renders_the_dashboard_not_help(self, tmp_path, monkeypatch):
        """Bare `kaira` inside a project shows the project, not the help page."""
        self._project(tmp_path, monkeypatch)
        result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "Usage:" not in result.output, "help page rendered instead of dashboard"
        assert "resources" in result.output
        assert "sqlite" in result.output
        assert "jwt" in result.output

    def test_dashboard_reports_project_metadata(self, tmp_path, monkeypatch):
        """The metadata block names the project, engine, auth and api version."""
        project = self._project(tmp_path, monkeypatch)
        (project / "models").mkdir()
        (project / "models" / "__init__.py").touch()
        (project / "models" / "user.py").touch()
        (project / "routers").mkdir()
        (project / "routers" / "user_router.py").touch()

        out = runner.invoke(app, []).output
        assert "api v1" in out
        assert "sqlite · demo" in out
        # __init__.py is package scaffolding, not a model.
        assert re.search(r"models\s+1", out)
        assert re.search(r"routers\s+1", out)

    def test_dashboard_detects_ci_from_disk(self, tmp_path, monkeypatch):
        """CI is read from the workflow file, not from an absent config key."""
        project = self._project(tmp_path, monkeypatch)
        assert "github" not in runner.invoke(app, []).output

        (project / ".github" / "workflows").mkdir(parents=True)
        assert "github" in runner.invoke(app, []).output

    def test_dashboard_lists_action_required_commands(self, tmp_path, monkeypatch):
        """Missing pieces surface as copy-pasteable commands."""
        self._project(tmp_path, monkeypatch)
        out = runner.invoke(app, []).output
        assert "action required" in out
        assert "kaira migrate init" in out
        assert "kaira auth generate --type jwt" in out

    def test_dashboard_outside_a_project(self, tmp_path, monkeypatch):
        """Outside a project the body points at init rather than erroring."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "no project here" in result.output
        assert "kaira init <project-name>" in result.output

    def test_malformed_config_does_not_crash(self, tmp_path, monkeypatch):
        """A broken .kaira.json reports itself instead of raising."""
        (tmp_path / ".kaira.json").write_text("{not json", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "malformed" in result.output
        assert "kaira config show" in result.output

    def test_help_still_renders_help(self, tmp_path, monkeypatch):
        """`kaira --help` keeps the grouped help page, banner on top."""
        self._project(tmp_path, monkeypatch)
        out = runner.invoke(app, ["--help"]).output
        assert "Usage:" in out
        assert "last action" not in out  # a dashboard-only line


# ---------------------------------------------------------------------------
# Section / step layout vocabulary
# ---------------------------------------------------------------------------


class TestLayoutVocabulary:
    def _render(self, capsys, fn, *args, **kwargs) -> list[str]:
        fn(*args, **kwargs)
        return capsys.readouterr().out.splitlines()

    def test_every_line_starts_in_the_gutter(self, capsys):
        """Sections, steps, notes, fields and hints share one left edge."""
        ui.section("scaffold", "demo")
        ui.field("database", "postgresql")
        ui.step("virtualenv", ".venv · 2.4s")
        ui.note("detected", "postgresql localhost:5432")
        ui.hint("kaira run")
        lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]

        assert lines, "nothing rendered"
        for line in lines:
            assert line.startswith(GUTTER), line

    def test_labels_align_across_steps_notes_and_fields(self, capsys):
        """A field's label lands in the same column as a step's label.

        A field carries no state symbol, so it has to be indented past the
        symbol column to keep the label column straight.
        """
        ui.step("virtualenv", ".venv")
        ui.note("detected", "localhost")
        ui.field("database", "postgresql")
        step_line, note_line, field_line = capsys.readouterr().out.splitlines()[:3]

        assert step_line.index("virtualenv") == note_line.index("detected")
        assert step_line.index("virtualenv") == field_line.index("database")

    def test_values_align_in_one_column(self, capsys):
        """Short and long labels put their values in the same column."""
        ui.step("ci", "github")
        ui.step("project files", "412ms")
        lines = capsys.readouterr().out.splitlines()
        assert lines[0].index("github") == lines[1].index("412ms")

    def test_oversized_label_keeps_a_separator(self, capsys):
        """A label past the column still keeps a space before its value."""
        ui.step("an extremely long step label", "detail")
        line = capsys.readouterr().out.splitlines()[0]
        assert "label detail" in line

    def test_subtext_aligns_under_the_value_column(self, capsys):
        """A continuation line sits under the value, not under the symbol."""
        ui.step("auth required", "postgres@localhost:5432")
        ui.subtext("blank to skip")
        first, second = capsys.readouterr().out.splitlines()[:2]
        assert first.index("postgres@") == second.index("blank to skip")

    def test_symbols_survive_the_ascii_fallback(self, monkeypatch, capsys):
        """`[ok]` must reach the terminal, not be eaten as a Rich style tag."""
        monkeypatch.setattr("kaira.core.theme.is_interactive", lambda: False)
        ui.step("project files", "42ms")
        ui.step("driver", "missing", State.FAILED)
        out = capsys.readouterr().out
        assert "[ok]" in out
        assert "[x]" in out

    def test_rule_never_spans_the_whole_terminal(self, monkeypatch, capsys):
        """Rules stay at the content width even on a very wide terminal."""
        monkeypatch.setattr("kaira.core.ui.terminal_width", lambda: 400)
        ui.rule()
        line = capsys.readouterr().out.splitlines()[0]
        assert len(line.strip()) == RULE_WIDTH

    def test_rule_shrinks_on_a_narrow_terminal(self, monkeypatch, capsys):
        """A rule wider than the terminal would wrap, so it is clamped."""
        monkeypatch.setattr("kaira.core.ui.terminal_width", lambda: 20)
        ui.rule()
        line = capsys.readouterr().out.splitlines()[0]
        assert len(line) <= 20

    def test_progress_block_shares_the_gutter(self):
        """The install block lines up with the surrounding step lines."""
        renderer, resolve, _download, _install = create_install_renderer(["a"], "uv")
        resolve.start()
        lines = [ln for ln in renderer.render_live().split("\n") if ln.strip()]
        assert all(strip_markup(line).startswith(GUTTER) for line in lines)


# ---------------------------------------------------------------------------
# Dependency array parsing (feeds the batched installer)
# ---------------------------------------------------------------------------


class TestDependencyParsing:
    PYPROJECT = """
[project]
name = "demo"
dependencies = [
    "fastapi[standard]>=0.115.0",
    "pydantic>=2.9.0,<3.0.0",

    # Auth dependencies
    "python-jose[cryptography]>=3.3.0",
    "alembic>=1.14.0",
]

[project.optional-dependencies]
dev = ["pytest"]
"""

    def test_extras_do_not_truncate_the_list(self):
        """A spec with extras must not end the array early.

        `fastapi[standard]` closes a bracket mid-spec; a non-greedy match stops
        there and silently drops every dependency after it.
        """
        specs = _parse_dependency_array(self.PYPROJECT)
        assert specs == [
            "fastapi[standard]>=0.115.0",
            "pydantic>=2.9.0,<3.0.0",
            "python-jose[cryptography]>=3.3.0",
            "alembic>=1.14.0",
        ]

    def test_comments_and_duplicates_are_dropped(self):
        """Comment lines are ignored and repeated specs collapse."""
        content = self.PYPROJECT.replace(
            '"alembic>=1.14.0",', '"alembic>=1.14.0",\n    "alembic>=1.14.0",'
        )
        specs = _parse_dependency_array(content)
        assert specs.count("alembic>=1.14.0") == 1
        assert not any(spec.startswith("#") for spec in specs)

    def test_missing_key_returns_empty(self):
        """A pyproject without the array yields nothing, not a crash."""
        assert _parse_dependency_array('[project]\nname = "demo"\n') == []


# ---------------------------------------------------------------------------
# GUIDE
# ---------------------------------------------------------------------------


class TestGuideCommands:
    def test_guide_commands_page(self):
        """kaira guide commands renders the guide panel."""
        result = runner.invoke(app, ["guide", "commands"])
        assert result.exit_code == 0
        assert "Static Command Reference Sheet" in result.output

    def test_guide_index_lists_the_page(self):
        """The guide index advertises the new page (drift guard)."""
        result = runner.invoke(app, ["guide"])
        assert result.exit_code == 0
        assert "kaira guide commands" in result.output


# ---------------------------------------------------------------------------
# Non-regression
# ---------------------------------------------------------------------------


class TestNonRegression:
    def test_deps_add_exits_1_when_install_fails(self, monkeypatch):
        """deps add still exits 1 on failure — rendering changed, not behaviour."""
        monkeypatch.setattr(
            "kaira.commands.project.install_packages", lambda *a, **k: (0, 1, 0)
        )
        result = runner.invoke(app, ["deps", "add", "kaira-fake-pkg"])
        assert result.exit_code == 1

    def test_deps_add_returns_a_result_tuple(self, fake_installer, monkeypatch):
        """install_packages returns counts its callers unpack."""
        calls, script = fake_installer
        monkeypatch.setattr(project_mod.shutil, "which", lambda name: None)
        script["lines"] = ["Successfully installed kaira-fake-a-1.0.0\n"]
        assert install_packages(["kaira-fake-a"]) == (1, 0, 0)

    def test_already_installed_packages_are_skipped_without_an_installer_run(
        self, fake_installer, monkeypatch
    ):
        """Nothing to do means no subprocess and a skipped count."""
        calls, _script = fake_installer
        installed, failed, skipped = install_packages(["pytest"])
        assert calls == []
        assert (installed, failed, skipped) == (0, 0, 1)
