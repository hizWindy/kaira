"""Tests for the Terminal Banner & CLI Identity phase.

Covers:
- The large lockup art: exact rows, exact width, no emoji.
- The composited shadow: grid shape, offset, and main winning every collision.
- The degradation ladder: one resolver, four tiers, each forced independently.
- The small lockup: mark, dynamic rule, cap, minimum length, optional version.
- Placement: the five named surfaces, and silence everywhere else.
"""

from __future__ import annotations

import pytest
from rich.cells import cell_len
from typer.testing import CliRunner

from kaira import __version__
from kaira.core import theme, ui
from kaira.main import app


runner = CliRunner()

MARK = "⚡ kaira"
BLOCK = "█"
RULE = "─"


@pytest.fixture(autouse=True)
def clean_banner_state():
    """Banner state is per-invocation; a leaked flag would silence other tests."""
    theme.reset_banner_cache()
    theme.set_quiet(False)
    yield
    theme.reset_banner_cache()
    theme.set_quiet(False)


@pytest.fixture()
def wide_tty(monkeypatch):
    """Present an interactive, colour, UTF-8, 80-column terminal."""
    monkeypatch.setattr("kaira.core.theme.banner_is_terminal", lambda: True)
    monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: True)
    monkeypatch.setattr("kaira.core.theme.is_interactive", lambda: True)
    monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 80)
    monkeypatch.delenv("NO_COLOR", raising=False)
    theme.reset_banner_cache()


def plain(lines) -> list[str]:
    """Reduce styled Rich ``Text`` lines to their characters."""
    return [line.plain for line in lines]


# ---------------------------------------------------------------------------
# The art
# ---------------------------------------------------------------------------


class TestBannerArt:
    def test_every_art_row_is_exactly_34_characters(self):
        """The composite indexes rows by column, so a short row shifts its shadow."""
        assert len(theme.BANNER_ART) == 5
        for row in theme.BANNER_ART:
            assert len(row) == theme.BANNER_ART_WIDTH == 34, repr(row)

    def test_art_is_drawn_from_one_glyph(self):
        """Only the block and the space — no emoji, no second block weight."""
        assert set("".join(theme.BANNER_ART)) == {BLOCK, " "}

    def test_tagline_copy_is_fixed(self):
        assert theme.BANNER_TAGLINE == "Continuous model-level FastAPI scaffolding"

    def test_large_banner_carries_no_emoji(self, wide_tty):
        """The block art carries the identity; the bolt belongs to the small mark."""
        rendered = "".join(plain(theme.large_banner_lines(shadow=True)))
        rendered += theme.large_banner_tagline().plain
        assert "⚡" not in rendered
        assert "⚙" not in rendered


# ---------------------------------------------------------------------------
# The composited shadow
# ---------------------------------------------------------------------------


class TestComposite:
    def test_grid_is_six_by_thirty_five(self):
        grid = theme.BANNER_COMPOSITE
        assert len(grid) == theme.COMPOSITE_ROWS == 6
        assert {len(row) for row in grid} == {theme.COMPOSITE_COLS} == {35}

    def test_grid_is_built_once_at_import(self):
        """Recomputing per invocation is the thing the cache exists to prevent."""
        assert theme.BANNER_COMPOSITE is theme.BANNER_COMPOSITE
        assert theme.BANNER_COMPOSITE == theme._build_composite()

    def test_main_layer_wins_every_collision(self):
        """Every art cell stays main, including the ones the shadow also claims."""
        grid = theme.BANNER_COMPOSITE
        collisions = 0
        for row, line in enumerate(theme.BANNER_ART):
            for col, char in enumerate(line):
                if char != BLOCK:
                    continue
                assert grid[row][col] == theme.MAIN, (row, col)
                # A cell the shadow would also have painted, had main not won.
                if row and col and theme.BANNER_ART[row - 1][col - 1] == BLOCK:
                    collisions += 1
        assert collisions, "no collisions to win — the offset is wrong"

    def test_shadow_sits_one_down_and_one_right(self):
        grid = theme.BANNER_COMPOSITE
        for row, line in enumerate(theme.BANNER_ART):
            for col, char in enumerate(line):
                if char == BLOCK and grid[row + 1][col + 1] != theme.MAIN:
                    assert grid[row + 1][col + 1] == theme.SHADOW, (row, col)

    def test_empty_cells_stay_empty(self):
        """Nothing paints outside the two layers."""
        painted = {theme.MAIN, theme.SHADOW, None}
        assert {cell for row in theme.BANNER_COMPOSITE for cell in row} <= painted

    def test_rows_carry_both_accent_and_shadow_spans(self, wide_tty):
        """A single row must be able to hold both layers — hence per-segment styling."""
        row = theme._composite_row(theme.BANNER_COMPOSITE[1])
        styles = {span.style for span in row.spans}
        assert theme.Theme.ACCENT_BANNER in styles
        assert theme.Theme.ACCENT_BANNER_DIM in styles

    def test_shadow_is_a_darker_stop_of_the_accent_hue(self):
        """One accent per project — the shadow is shade, not a second colour."""
        from rich.color import Color

        accent = Color.parse(theme.Theme.ACCENT_BANNER).get_truecolor()
        dim = Color.parse(theme.Theme.ACCENT_BANNER_DIM).get_truecolor()
        assert sum(dim) < sum(accent)

        import colorsys

        accent_hue = colorsys.rgb_to_hsv(*[c / 255 for c in accent])[0]
        dim_hue = colorsys.rgb_to_hsv(*[c / 255 for c in dim])[0]
        assert abs(accent_hue - dim_hue) < 0.02

    def test_flat_layer_is_the_art_verbatim(self, wide_tty):
        """Tier 2 drops the shadow rather than restyling the art."""
        lines = plain(theme.large_banner_lines(shadow=False))
        assert len(lines) == 5
        for line, row in zip(lines, theme.BANNER_ART):
            assert line == theme.BANNER_INDENT + row.rstrip()

    def test_composited_layer_is_six_indented_rows(self, wide_tty):
        lines = plain(theme.large_banner_lines(shadow=True))
        assert len(lines) == 6
        assert all(line.startswith(theme.BANNER_INDENT) for line in lines)


# ---------------------------------------------------------------------------
# The degradation ladder
# ---------------------------------------------------------------------------


class TestDegradationLadder:
    def test_tier1_wide_colour_utf8(self, wide_tty):
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_LARGE_SHADOW

    def test_tier1_floor_is_44_columns(self, wide_tty, monkeypatch):
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 44)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_LARGE_SHADOW

    def test_tier2_under_no_color(self, wide_tty, monkeypatch):
        """Without colour the two layers are the same glyph, so the shadow goes."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr("kaira.core.theme.is_interactive", lambda: False)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_LARGE_FLAT

    def test_tier2_between_40_and_43_columns(self, wide_tty, monkeypatch):
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 43)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_LARGE_FLAT

    def test_tier3_below_40_columns(self, wide_tty, monkeypatch):
        """Narrow drops a tier — it never clips, wraps, or scales the art."""
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 39)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_SMALL

    def test_tier3_for_every_small_surface(self, wide_tty):
        assert theme.resolve_banner_tier(theme.SURFACE_SMALL) == theme.TIER_SMALL

    def test_tier3_on_non_tty_however_wide(self, wide_tty, monkeypatch):
        """Piped output never gets block art, no matter how wide the pipe."""
        monkeypatch.setattr("kaira.core.theme.banner_is_terminal", lambda: False)
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 200)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_SMALL

    def test_tier4_without_utf8(self, wide_tty, monkeypatch):
        """No UTF-8 means no art, no bolt and no rule left to degrade to."""
        monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: False)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_PLAIN
        assert theme.resolve_banner_tier(theme.SURFACE_SMALL) == theme.TIER_PLAIN

    def test_tier4_line_is_plain_ascii(self):
        line = theme.plain_banner_line("1.0.0")
        assert line == "kaira v1.0.0"
        assert line.isascii()

    def test_tier_is_resolved_once_per_invocation(self, wide_tty, monkeypatch):
        """The ladder is cached; a per-line re-check is how a banner disagrees
        with itself halfway down."""
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_LARGE_SHADOW
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 10)
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_LARGE_SHADOW
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_LARGE) == theme.TIER_SMALL

    def test_width_comes_from_rich(self, monkeypatch):
        """Rich already resolves the redirected and non-TTY cases."""
        from kaira.console import console

        assert theme.banner_width() == console.size.width


# ---------------------------------------------------------------------------
# The small lockup
# ---------------------------------------------------------------------------


class TestSmallBanner:
    def test_composition_is_mark_rule_version(self, wide_tty):
        text = theme.small_banner_line("1.0.0").plain
        assert text.startswith(MARK + " ")
        assert text.endswith(" v1.0.0")
        assert RULE * theme.SMALL_BANNER_MIN_RULE in text

    def test_name_is_always_lowercase(self, wide_tty):
        assert theme.SMALL_BANNER_NAME == "kaira"
        assert "Kaira" not in theme.small_banner_line("1.0.0").plain

    def test_rule_fills_the_line_exactly(self, wide_tty):
        assert cell_len(theme.small_banner_line("1.0.0").plain) == 80

    def test_rule_is_capped_at_80_columns(self, wide_tty, monkeypatch):
        """A rule across a 200-column window looks broken, not impressive."""
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 200)
        assert cell_len(theme.small_banner_line("1.0.0").plain) == 80

    def test_version_is_omittable(self, wide_tty):
        """Omitted, the rule runs to the right margin instead of stopping short."""
        with_version = theme.small_banner_line("1.0.0").plain
        without = theme.small_banner_line(None).plain
        assert "v1.0.0" not in without
        assert cell_len(without) == cell_len(with_version) == 80
        assert without.count(RULE) > with_version.count(RULE)

    def test_rule_is_dropped_rather_than_truncated(self, wide_tty, monkeypatch):
        """Below four characters there is no rule worth drawing."""
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 17)
        text = theme.small_banner_line("1.0.0").plain
        assert text == f"{MARK} v1.0.0"
        assert RULE not in text

    def test_rule_survives_at_exactly_four_characters(self, wide_tty, monkeypatch):
        # mark (8 cells) + version (6) + 2 padding + 4 rule
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 20)
        assert theme.small_banner_line("1.0.0").plain.count(RULE) == 4

    def test_rule_never_wraps_to_a_second_line(self, wide_tty, monkeypatch):
        """The bolt is double-width, so cell width — not len — decides the fit.

        Under a terminal too narrow to hold even the mark the line collapses to
        the un-ruled fallback and stops there; what it must never do is grow a
        rule that pushes past the margin.
        """
        bare = f"{MARK} v1.0.0"
        for width in range(10, 90):
            monkeypatch.setattr("kaira.core.theme.banner_width", lambda w=width: w)
            text = theme.small_banner_line("1.0.0").plain
            assert "\n" not in text
            assert cell_len(text) <= max(min(width, 80), cell_len(bare)), width

    def test_bolt_is_the_only_emoji(self, wide_tty):
        text = theme.small_banner_line("1.0.0").plain
        assert text.count("⚡") == 1
        assert "⚙" not in text

    def test_bolt_shares_the_attribution_utf8_gate(self, wide_tty, monkeypatch):
        """One UTF-8 gate for the whole project — this is Phase 5.5's."""
        monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: False)
        theme.reset_banner_cache()
        assert theme.resolve_banner_tier(theme.SURFACE_SMALL) == theme.TIER_PLAIN
        assert "⚡" not in theme.plain_banner_line("1.0.0")
        assert theme.attribution() == "Created by Khair"

    def test_parts_are_styled_from_theme_tokens(self, wide_tty):
        styles = {span.style for span in theme.small_banner_line("1.0.0").spans}
        assert theme.Theme.ACCENT_BANNER in styles
        assert theme.Theme.ACCENT_BANNER_DIM in styles
        assert theme.Theme.MUTED in styles


# ---------------------------------------------------------------------------
# Rendering through the tiers
# ---------------------------------------------------------------------------


class TestRendering:
    def _render(self, capsys, fn, **kwargs) -> str:
        fn(**kwargs)
        return capsys.readouterr().out

    def test_large_surface_tier1_prints_the_composite(self, capsys, wide_tty):
        out = self._render(capsys, ui.render_large_banner)
        assert out.count(BLOCK) > 100
        assert theme.BANNER_TAGLINE in out

    def test_large_surface_tier3_prints_the_small_mark(
        self, capsys, wide_tty, monkeypatch
    ):
        monkeypatch.setattr("kaira.core.theme.banner_width", lambda: 30)
        theme.reset_banner_cache()
        out = self._render(capsys, ui.render_large_banner)
        assert BLOCK not in out
        assert MARK in out

    def test_large_surface_tier4_prints_plain_ascii(
        self, capsys, wide_tty, monkeypatch
    ):
        monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: False)
        theme.reset_banner_cache()
        out = self._render(capsys, ui.render_large_banner)
        assert out.strip() == f"kaira v{__version__}"

    def test_small_surface_tier4_prints_plain_ascii(
        self, capsys, wide_tty, monkeypatch
    ):
        monkeypatch.setattr("kaira.core.theme.supports_utf8", lambda: False)
        theme.reset_banner_cache()
        out = self._render(capsys, ui.render_small_banner)
        assert out.strip() == f"kaira v{__version__}"

    def test_large_banner_is_framed_by_blank_lines(self, capsys, wide_tty):
        """One blank above, one between art and tagline, one below."""
        out = self._render(capsys, ui.render_large_banner).split("\n")
        assert out[0] == ""
        art = [i for i, line in enumerate(out) if BLOCK in line]
        tagline = next(i for i, line in enumerate(out) if theme.BANNER_TAGLINE in line)
        assert out[art[-1] + 1] == ""
        assert tagline == art[-1] + 2
        assert out[tagline + 1] == ""

    def test_every_large_banner_line_shares_the_indent(self, capsys, wide_tty):
        """Two spaces on banner and tagline alike.

        The final row is shadow only, so it starts one column further right —
        that column *is* the offset, not a stray space.
        """
        out = self._render(capsys, ui.render_large_banner)
        indents = {
            len(line) - len(line.lstrip()) for line in out.split("\n") if line.strip()
        }
        assert indents <= {len(theme.BANNER_INDENT), len(theme.BANNER_INDENT) + 1}
        tagline = next(line for line in out.split("\n") if theme.BANNER_TAGLINE in line)
        assert tagline == theme.BANNER_INDENT + theme.BANNER_TAGLINE

    def test_quiet_suppresses_both_banners(self, capsys, wide_tty):
        theme.set_quiet(True)
        assert self._render(capsys, ui.render_large_banner) == ""
        assert self._render(capsys, ui.render_small_banner) == ""


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


BANNER_SURFACES = [
    pytest.param([], id="bare"),
    pytest.param(["--version"], id="version"),
    pytest.param(["about"], id="about"),
    pytest.param(["commands"], id="commands"),
    pytest.param(["init"], id="init"),
]


@pytest.fixture()
def stub_init(monkeypatch):
    """`kaira init` scaffolds a whole project; the banner lands before any of it."""
    calls: list[dict] = []
    monkeypatch.setattr("kaira.main.init_command", lambda **kw: calls.append(kw))
    return calls


class TestPlacement:
    @pytest.mark.parametrize("argv", BANNER_SURFACES)
    def test_named_surfaces_render_a_banner(
        self, argv, tmp_path, monkeypatch, stub_init
    ):
        monkeypatch.chdir(tmp_path)
        out = runner.invoke(app, argv).output
        assert MARK in out or BLOCK in out

    @pytest.mark.parametrize("argv", BANNER_SURFACES)
    def test_no_surface_renders_a_banner_twice(
        self, argv, tmp_path, monkeypatch, stub_init
    ):
        """Once per invocation, ever — one function, one call site per surface."""
        monkeypatch.chdir(tmp_path)
        out = runner.invoke(app, argv).output
        assert out.count(MARK) <= 1

    @pytest.mark.parametrize(
        "argv",
        [
            ["--help"],
            ["check"],
            ["info"],
            ["list", "--help"],
            ["guide"],
            ["docker", "--help"],
            ["generate", "--help"],
        ],
    )
    def test_no_banner_outside_the_named_surfaces(self, argv, tmp_path, monkeypatch):
        """A banner on every command is noise and destroys the large one's ceremony."""
        monkeypatch.chdir(tmp_path)
        out = runner.invoke(app, argv).output
        assert MARK not in out
        assert BLOCK not in out
        assert theme.BANNER_TAGLINE not in out

    @pytest.mark.parametrize("argv", BANNER_SURFACES)
    def test_quiet_suppresses_the_banner_on_every_surface(
        self, argv, tmp_path, monkeypatch, stub_init
    ):
        monkeypatch.chdir(tmp_path)
        out = runner.invoke(app, ["--quiet", *argv]).output
        assert MARK not in out
        assert BLOCK not in out

    def test_quiet_is_found_wherever_it_appears(self, tmp_path, monkeypatch):
        """`--version` is eager, so the flag is read before any callback runs."""
        monkeypatch.chdir(tmp_path)
        assert MARK not in runner.invoke(app, ["--version", "--quiet"]).output

    def test_non_tty_output_contains_no_block_characters(
        self, tmp_path, monkeypatch, stub_init
    ):
        """`kaira init > log.txt` must produce a readable log, not 200 blocks."""
        monkeypatch.chdir(tmp_path)
        assert BLOCK not in runner.invoke(app, ["init"]).output

    def test_init_still_scaffolds(self, tmp_path, monkeypatch, stub_init):
        """This phase is additive to output: init's arguments are untouched."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "demo", "--db", "sqlite"])
        assert result.exit_code == 0
        assert stub_init == [
            {
                "name": "demo",
                "db": "sqlite",
                "auth": None,
                "docker": None,
                "ci": None,
                "profile": None,
                "yes": False,
            }
        ]

    def test_bare_kaira_omits_the_version_from_the_mark(self, tmp_path, monkeypatch):
        """The dashboard body already states it; repeating it shortens the rule."""
        monkeypatch.chdir(tmp_path)
        banner = runner.invoke(app, []).output.split("\n")[0]
        assert MARK in banner
        assert f"v{__version__}" not in banner

    def test_version_surface_keeps_its_version_line(self, tmp_path, monkeypatch):
        """Non-regression: the banner is additive, the surface still reports."""
        monkeypatch.chdir(tmp_path)
        out = runner.invoke(app, ["--version"]).output
        assert f"Kaira v{__version__}" in out
        assert "Created by Khair" in out

    def test_help_still_renders_help(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out = runner.invoke(app, ["--help"]).output
        assert "Usage:" in out

    def test_attribution_stays_off_project_creation(
        self, tmp_path, monkeypatch, stub_init
    ):
        """Phase 5.5 owns that surface — it belongs on `about` and `--version`."""
        monkeypatch.chdir(tmp_path)
        assert "Created by Khair" not in runner.invoke(app, ["init"]).output
