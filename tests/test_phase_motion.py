"""Tests for the motion layer and the redesigned welcome surface.

Motion is only acceptable if it cannot cost anything, so the properties tested
here are the ones that keep that true:

- **Bounded** — one budget per invocation, shared by every effect, and the
  per-step delay divides it rather than multiplying it: a longer surface
  animates faster rather than taking longer, and a surface too long to animate
  inside the budget prints at once instead of overrunning.
- **Additive** — an animated surface prints the same lines, in the same order,
  as the still one.  Timing is the only difference.
- **Optional** — a pipe, ``NO_COLOR``, ``CI``, ``--quiet`` and
  ``KAIRA_NO_MOTION`` each turn it off on their own.

Plus the overview vocabulary the new dashboard is built from, and the dashboard
itself.
"""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from kaira.core import motion, theme, ui
from kaira.core.progress import State
from kaira.main import app


runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Motion and banner state are per-invocation; a leak would silence others."""
    for name in motion.DISABLE_ENV_VARS + motion.CI_ENV_VARS + ("NO_COLOR",):
        monkeypatch.delenv(name, raising=False)
    theme.reset_banner_cache()
    theme.set_quiet(False)
    motion.reset_budget()
    yield
    theme.reset_banner_cache()
    theme.set_quiet(False)
    motion.reset_budget()


@pytest.fixture()
def live_terminal(monkeypatch):
    """Present a live, colour, UTF-8 terminal so motion is permitted."""
    monkeypatch.setattr("kaira.core.motion.is_interactive", lambda: True)
    monkeypatch.setattr("kaira.core.motion.banner_is_terminal", lambda: True)
    monkeypatch.setattr("kaira.core.motion.time.sleep", lambda _s: None)


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


class TestMotionGate:
    def test_a_live_terminal_may_animate(self, live_terminal):
        assert motion.motion_enabled() is True

    def test_a_pipe_may_not(self, monkeypatch):
        monkeypatch.setattr("kaira.core.motion.is_interactive", lambda: True)
        monkeypatch.setattr("kaira.core.motion.banner_is_terminal", lambda: False)
        assert motion.motion_enabled() is False

    def test_no_color_turns_it_off(self, live_terminal, monkeypatch):
        """NO_COLOR is the standing signal for plain output, motion included."""
        monkeypatch.setattr(
            "kaira.core.motion.is_interactive", theme.is_interactive
        )
        monkeypatch.setenv("NO_COLOR", "1")
        assert motion.motion_enabled() is False

    @pytest.mark.parametrize("var", motion.CI_ENV_VARS)
    def test_ci_turns_it_off(self, live_terminal, monkeypatch, var):
        monkeypatch.setenv(var, "true")
        assert motion.motion_enabled() is False

    @pytest.mark.parametrize("var", motion.DISABLE_ENV_VARS)
    def test_the_opt_out_is_honoured(self, live_terminal, monkeypatch, var):
        monkeypatch.setenv(var, "1")
        assert motion.motion_enabled() is False

    def test_quiet_turns_it_off(self, live_terminal):
        theme.set_quiet(True)
        assert motion.motion_enabled() is False


# ---------------------------------------------------------------------------
# The budget
# ---------------------------------------------------------------------------


class TestBudget:
    @pytest.mark.parametrize("count", [2, 5, 12, 40, 200])
    def test_the_whole_effect_fits_inside_the_budget(self, count):
        """More lines must mean a faster cascade, never a longer one."""
        delay = motion._step_delay(count, motion.MOTION_BUDGET_S)
        assert delay * count <= motion.MOTION_BUDGET_S

    def test_a_short_effect_does_not_crawl(self):
        assert motion._step_delay(2, motion.MOTION_BUDGET_S) <= motion.MAX_STEP_S

    def test_a_single_line_has_nothing_to_stagger(self):
        assert motion._step_delay(1, motion.MOTION_BUDGET_S) == 0.0

    def test_too_many_frames_for_the_budget_means_no_motion(self):
        """A step below the floor is a flicker; better to print at once."""
        frames = int(motion.MOTION_BUDGET_S / motion.MIN_STEP_S) + 50
        assert motion._step_delay(frames, motion.MOTION_BUDGET_S) == 0.0

    def test_an_exhausted_pool_means_no_motion(self):
        assert motion._step_delay(5, 0.0) == 0.0

    def test_the_budget_stays_under_the_immediacy_threshold(self):
        """Past roughly 400ms a terminal stops feeling like it answered."""
        assert motion.MOTION_BUDGET_S <= 0.4

    def test_the_default_shares_fit_inside_the_pool(self):
        """A banner sweep plus a dashboard cascade is one invocation, one budget."""
        assert motion.PLAY_BUDGET_S + motion.REVEAL_BUDGET_S <= motion.MOTION_BUDGET_S

    def test_the_pool_is_shared_across_effects(self):
        """Two effects must split one budget, not each take a full one."""
        first = motion._claim(0.30)
        second = motion._claim(0.30)
        assert first == pytest.approx(0.30)
        assert first + second <= motion.MOTION_BUDGET_S

    def test_the_pool_refills_for_a_new_invocation(self):
        motion._claim(motion.MOTION_BUDGET_S)
        assert motion.budget_remaining() == 0.0
        motion.reset_budget()
        assert motion.budget_remaining() == motion.MOTION_BUDGET_S

    def test_a_second_surface_in_one_invocation_cannot_overrun(self, live_terminal):
        """Whatever the call order, the sleeps in one invocation are capped."""
        slept: list[float] = []
        import kaira.core.motion as m

        original = m.time.sleep
        try:
            m.time.sleep = slept.append
            for _ in range(4):
                motion.reveal([f"line {i}" for i in range(12)], printer=lambda _l: None)
        finally:
            m.time.sleep = original
        assert sum(slept) <= motion.MOTION_BUDGET_S


# ---------------------------------------------------------------------------
# Reveal
# ---------------------------------------------------------------------------


class TestReveal:
    def test_still_output_prints_every_line_once_in_order(self):
        seen: list[str] = []
        motion.reveal(["a", "b", "c"], printer=seen.append)
        assert seen == ["a", "b", "c"]

    def test_animated_output_is_the_same_lines(self, live_terminal):
        """The animation adds pauses, never characters."""
        seen: list[str] = []
        motion.reveal(["a", "", "b"], printer=seen.append)
        assert seen == ["a", "", "b"]

    def test_blank_lines_are_not_paused_on(self, live_terminal, monkeypatch):
        """Spacing is not a beat — pausing on it starves the lines with text."""
        slept: list[float] = []
        monkeypatch.setattr("kaira.core.motion.time.sleep", slept.append)
        motion.reveal(["a", "", "", "b"], printer=lambda _line: None)
        assert len(slept) == 2

    def test_an_interrupt_flushes_the_rest(self, live_terminal, monkeypatch):
        """Ctrl-C asks for the rest now, not for half a surface."""
        seen: list[str] = []

        def printer(line):
            seen.append(line)
            if line == "b":
                raise KeyboardInterrupt

        monkeypatch.setattr("kaira.core.motion.time.sleep", lambda _s: None)
        motion.reveal(["a", "b", "c", "d"], printer=printer)
        assert seen == ["a", "b", "c", "d"]

    def test_the_default_sink_is_the_shared_console(self, capsys):
        motion.reveal(["hello"])
        assert "hello" in capsys.readouterr().out


class TestPlay:
    def test_without_motion_only_the_final_frame_prints(self, capsys):
        motion.play(["one", "two"], "final")
        out = capsys.readouterr().out
        assert "final" in out
        assert "one" not in out

    def test_the_final_frame_is_what_survives(self, live_terminal, capsys):
        motion.play(["one", "two"], "final")
        assert capsys.readouterr().out.strip().endswith("final")

    def test_no_frames_still_prints_the_final(self, live_terminal, capsys):
        motion.play([], "final")
        assert "final" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The banner sweep
# ---------------------------------------------------------------------------


class TestBannerSweep:
    @pytest.fixture(autouse=True)
    def wide_tty(self, monkeypatch):
        monkeypatch.setattr("kaira.core.theme.banner_is_terminal", lambda: True)
        monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: True)
        monkeypatch.setattr("kaira.core.theme.is_interactive", lambda: True)
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 80)
        theme.reset_banner_cache()

    def test_every_frame_is_the_still_line(self):
        """Geometry never changes, so the mark cannot shift as the sweep passes."""
        still = theme.small_banner_line("1.0.0").plain
        for frame in theme.small_banner_sweep("1.0.0"):
            assert frame.plain == still

    def test_the_sweep_lights_a_run_and_moves_it(self):
        frames = theme.small_banner_sweep("1.0.0")
        lit = [
            [
                span.start
                for span in frame.spans
                if span.style == theme.Theme.ACCENT_BANNER_BRIGHT
            ]
            for frame in frames
        ]
        starts = [min(positions) for positions in lit if positions]
        assert starts == sorted(starts)
        assert len(set(starts)) > 1, "the highlight never moved"

    def test_a_narrow_terminal_has_nothing_to_sweep(self, monkeypatch):
        """No rule means no sweep — animating the bare mark would only jitter."""
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 17)
        assert theme.small_banner_sweep("1.0.0") == []

    def test_the_bright_stop_is_the_accent_hue_lifted(self):
        import colorsys

        from rich.color import Color

        accent = Color.parse(theme.Theme.ACCENT_BANNER).get_truecolor()
        bright = Color.parse(theme.Theme.ACCENT_BANNER_BRIGHT).get_truecolor()
        assert sum(bright) > sum(accent)

        accent_hue = colorsys.rgb_to_hsv(*[c / 255 for c in accent])[0]
        bright_hue = colorsys.rgb_to_hsv(*[c / 255 for c in bright])[0]
        assert abs(accent_hue - bright_hue) < 0.02


# ---------------------------------------------------------------------------
# The overview vocabulary
# ---------------------------------------------------------------------------


class TestOverviewVocabulary:
    @pytest.fixture(autouse=True)
    def utf8_terminal(self, monkeypatch):
        """sym() degrades to ASCII off a TTY; these assert the glyph forms."""
        monkeypatch.setattr("kaira.core.theme.is_interactive", lambda: True)

    def _plain(self, markup: str) -> str:
        from rich.text import Text

        return Text.from_markup(markup).plain

    def test_a_meter_fills_in_proportion(self):
        from kaira.core.theme import METER_WIDTH

        full = self._plain(ui.fmt_meter(4, 4, "setup"))
        half = self._plain(ui.fmt_meter(2, 4, "setup"))
        assert full.count("█") == METER_WIDTH
        assert half.count("█") == METER_WIDTH // 2

    def test_a_meter_states_its_fraction(self):
        assert "3/5" in self._plain(ui.fmt_meter(3, 5, "setup"))

    def test_a_meter_of_nothing_does_not_divide_by_zero(self):
        assert "0/0" in self._plain(ui.fmt_meter(0, 0, "setup"))

    @pytest.mark.parametrize("width", [36, 40, 52, 80, 200])
    def test_a_meter_never_wraps(self, monkeypatch, width):
        """A meter that runs onto a second line has lost what it was for."""
        monkeypatch.setattr("kaira.core.ui.terminal_width", lambda: width)
        assert len(self._plain(ui.fmt_meter(2, 5, "setup"))) <= width

    def test_a_narrow_meter_keeps_a_readable_bar(self, monkeypatch):
        from kaira.core.theme import METER_MIN_WIDTH

        monkeypatch.setattr("kaira.core.ui.terminal_width", lambda: 36)
        line = self._plain(ui.fmt_meter(2, 5, "setup"))
        assert line.count("█") + line.count("░") >= METER_MIN_WIDTH

    @pytest.mark.parametrize("width", [36, 40, 52, 80])
    def test_stats_tighten_rather_than_wrap(self, monkeypatch, width):
        monkeypatch.setattr("kaira.core.ui.terminal_width", lambda: width)
        line = self._plain(
            ui.fmt_stats([("models", "1"), ("routers", "0"), ("tests", "0")])
        )
        assert len(line) <= width

    def test_a_headline_pushes_its_badge_to_the_margin(self):
        line = self._plain(ui.fmt_headline("myproject", ui.fmt_pill("online")))
        assert line.startswith("  myproject")
        assert line.rstrip().endswith("online")
        assert "   " in line, "the badge was not pushed right"

    def test_a_headline_drops_a_badge_it_cannot_fit(self, monkeypatch):
        """Better no badge than one wrapped onto a line of its own."""
        monkeypatch.setattr("kaira.core.ui.terminal_width", lambda: 12)
        line = self._plain(ui.fmt_headline("a-long-project-name", ui.fmt_pill("online")))
        assert "online" not in line

    def test_a_headline_without_a_badge_is_just_the_title(self):
        assert self._plain(ui.fmt_headline("myproject")) == "  myproject"

    def test_stats_sit_on_one_line(self):
        line = self._plain(ui.fmt_stats([("models", "3"), ("routers", "2")]))
        assert "\n" not in line
        assert re.search(r"models\s+3", line)
        assert re.search(r"routers\s+2", line)

    def test_a_pill_is_a_dot_not_a_verdict(self):
        assert "●" in self._plain(ui.fmt_pill("online", State.DONE))
        assert "○" in self._plain(ui.fmt_pill("none", State.PENDING, filled=False))

    def test_the_formatters_and_the_printers_agree(self, capsys):
        """Two spellings of one layout is how two surfaces drift apart."""
        pairs = [
            (ui.fmt_step, ui.step, ("connection", "online")),
            (ui.fmt_field, ui.field, ("database", "sqlite")),
            (ui.fmt_hint, ui.hint, ("kaira run",)),
            (ui.fmt_note, ui.note, ("looked for", ".kaira.json")),
            (ui.fmt_caption, ui.caption, ("api v1",)),
            (ui.fmt_headline, ui.headline, ("proj29", ui.fmt_pill("online"))),
            (ui.fmt_meter, ui.meter, (2, 5, "setup")),
            (ui.fmt_stats, ui.stats, ([("models", "3")],)),
        ]
        for formatter, printer, args in pairs:
            printer(*args)
            printed = capsys.readouterr().out.rstrip("\n")
            assert printed == self._plain(formatter(*args)).rstrip()


# ---------------------------------------------------------------------------
# The welcome surface
# ---------------------------------------------------------------------------


class TestWelcomeSurface:
    def _project(self, tmp_path, monkeypatch, **overrides):
        import json

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

    def test_the_setup_meter_counts_what_is_done(self, tmp_path, monkeypatch):
        """A bare project has its database, and no routers left untested."""
        self._project(tmp_path, monkeypatch)
        out = runner.invoke(app, []).output
        assert "setup" in out
        assert "2/5" in out

    def test_the_meter_and_the_action_list_never_disagree(self, tmp_path, monkeypatch):
        """Both are derived from one checklist, so the counts must line up."""
        project = self._project(tmp_path, monkeypatch)
        (project / "auth").mkdir()
        (project / "auth" / "dependencies.py").touch()
        (project / "Dockerfile").touch()

        out = runner.invoke(app, []).output
        done = int(re.search(r"(\d+)/5", out).group(1))
        # The arrow degrades to ASCII off a TTY, so the commands are counted by
        # their text rather than by the bullet in front of them.
        block = out.split("action required")[1].split("next")[0]
        actions = len(re.findall(r"kaira [a-z-]+", block))
        assert done == 4
        assert actions == 5 - done

    def test_a_finished_project_lists_no_actions(self, tmp_path, monkeypatch):
        project = self._project(tmp_path, monkeypatch)
        for path in ("auth/dependencies.py", "alembic/env.py"):
            (project / path).parent.mkdir(parents=True, exist_ok=True)
            (project / path).touch()
        (project / "Dockerfile").touch()

        out = runner.invoke(app, []).output
        assert "5/5" in out
        assert "action required" not in out

    def test_the_headline_names_the_project_and_its_mode(self, tmp_path, monkeypatch):
        self._project(tmp_path, monkeypatch, project="myproject")
        out = runner.invoke(app, []).output
        assert "myproject" in out
        assert "online" in out

    def test_the_auth_type_is_named_even_when_unconfigured(self, tmp_path, monkeypatch):
        """'not configured' alone leaves the reader guessing not configured as what."""
        self._project(tmp_path, monkeypatch)
        out = runner.invoke(app, []).output
        assert re.search(r"auth setup\s+jwt · not configured", out)

    def test_a_running_server_is_reported_at_its_real_address(
        self, tmp_path, monkeypatch
    ):
        """The dashboard must not say 'down' about a server shifted off 8000."""
        self._project(tmp_path, monkeypatch)
        monkeypatch.setattr(
            "kaira.core.ports.read_server", lambda root=None: ("127.0.0.1", 8001)
        )
        out = runner.invoke(app, []).output
        assert "http://127.0.0.1:8001" in out

    def test_no_server_line_when_nothing_is_running(self, tmp_path, monkeypatch):
        self._project(tmp_path, monkeypatch)
        monkeypatch.setattr("kaira.core.ports.read_server", lambda root=None: None)
        assert "http://" not in runner.invoke(app, []).output

    def test_the_animated_body_is_the_still_body(self, tmp_path, monkeypatch, capsys):
        """The whole point of composing first: motion changes timing, not text."""
        from kaira.commands.dashboard import welcome_dashboard

        self._project(tmp_path, monkeypatch)

        welcome_dashboard()
        still = capsys.readouterr().out

        monkeypatch.setattr("kaira.core.motion.motion_enabled", lambda: True)
        monkeypatch.setattr("kaira.core.motion.time.sleep", lambda _s: None)
        welcome_dashboard()
        animated = capsys.readouterr().out

        assert animated == still

    def test_quiet_keeps_the_body(self, tmp_path, monkeypatch):
        """--quiet drops the banner and the motion, not the answer."""
        self._project(tmp_path, monkeypatch)
        out = runner.invoke(app, ["--quiet"]).output
        assert "setup" in out
        assert "⚡ kaira" not in out
