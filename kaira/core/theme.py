"""Kaira terminal design system — single source of truth for all UI.

All new commands must import from this module instead of defining
inline colours or symbols.  Contains the banner lockup, progress state
symbols, and the three-tier degradation system.
"""

from __future__ import annotations

import itertools
import os
import shutil
import sys
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from rich.text import Text


# ---------------------------------------------------------------------------
# Interactive detection helper
# ---------------------------------------------------------------------------


def is_interactive() -> bool:
    """Return True when running in a real interactive terminal.

    Conditions that disable interactive mode (both must pass):
    - stdout is a TTY
    - The ``NO_COLOR`` environment variable is NOT set

    In CI, piped output, or scripts the function returns False so callers
    degrade to plain-text output with no ANSI escape codes.

    Returns:
        bool: True if the output should include Rich markup / animations.
    """
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def supports_utf8() -> bool:
    """Return True when stdout can safely render non-ASCII (UTF-8) text.

    Used to gate the Arabic form of the attribution so it degrades to a
    Latin-only fallback on legacy Windows code pages rather than risking
    mojibake next to the ⚡ glyph.
    """
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in encoding


def terminal_width() -> int:
    """Return the current terminal width in columns.

    Falls back to 80 when the width cannot be determined (e.g. piped output).

    Returns:
        int: Terminal width in columns.
    """
    return shutil.get_terminal_size((80, 24)).columns


# ---------------------------------------------------------------------------
# Attribution — single source of truth (never hardcode per surface)
# ---------------------------------------------------------------------------

AUTHOR_NAME = "Khair"
AUTHOR_ARABIC = "خير"
PROJECT_URL = "github.com/khair/kaira"


def attribution() -> str:
    """Return the attribution line, UTF-8-gated with a Latin-only fallback."""
    if supports_utf8():
        return f"Created by {AUTHOR_NAME} · {AUTHOR_ARABIC}"
    return f"Created by {AUTHOR_NAME}"


# ---------------------------------------------------------------------------
# Layout — one content width for every Kaira surface
# ---------------------------------------------------------------------------

RULE_WIDTH = 44
"""Width of section rules and progress rules.

Output is laid out against a fixed content column rather than the terminal
width: a rule or panel stretched across a 200-column window puts the eye a long
way from the text it belongs to.
"""

GUTTER = "  "
"""Left gutter every step, field, and rule is indented by."""

LABEL_WIDTH = 14
"""Column the step/field label is padded to, so values line up."""


# ---------------------------------------------------------------------------
# Banner — two lockups, one hierarchy
#
# Kaira has exactly two banners and they do different jobs.  The large block
# lockup is ceremony for ``kaira init`` — the one moment a project begins.  The
# small mark is wayfinding on surfaces the user returns to daily, and doubles
# as a section divider so it earns its line instead of only decorating it.
#
# The art, the composite, the degradation ladder and the quiet gate all live
# here so no command has to reason about terminal capability on its own.
# ---------------------------------------------------------------------------

BANNER_BLOCK = "\u2588"
"""The single glyph the large lockup is drawn from."""

BANNER_ART: tuple[str, ...] = (
    "\u2588\u2588  \u2588\u2588  \u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588 \u2588\u2588\u2588\u2588\u2588   \u2588\u2588\u2588\u2588 ",
    "\u2588\u2588 \u2588\u2588  \u2588\u2588  \u2588\u2588   \u2588\u2588   \u2588\u2588  \u2588\u2588 \u2588\u2588  \u2588\u2588",
    "\u2588\u2588\u2588\u2588   \u2588\u2588\u2588\u2588\u2588\u2588   \u2588\u2588   \u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588",
    "\u2588\u2588 \u2588\u2588  \u2588\u2588  \u2588\u2588   \u2588\u2588   \u2588\u2588 \u2588\u2588  \u2588\u2588  \u2588\u2588",
    "\u2588\u2588  \u2588\u2588 \u2588\u2588  \u2588\u2588 \u2588\u2588\u2588\u2588\u2588\u2588 \u2588\u2588  \u2588\u2588 \u2588\u2588  \u2588\u2588",
)
"""The large lockup, 5 rows on a strict 34-column grid.

Trailing spaces are part of the grid, not slack — the composite in
:data:`BANNER_COMPOSITE` indexes into these rows by column, so a row short by
one character would shift its own shadow.  A test asserts the width.
"""

BANNER_ART_WIDTH = 34
"""Every row of :data:`BANNER_ART` is exactly this many characters."""

BANNER_TAGLINE = "Continuous model-level FastAPI scaffolding"
"""Fixed copy under the large lockup. Sentence case, no version, no hype."""

BANNER_INDENT = "  "
"""Two-column left indent shared by the lockup rows and the tagline."""


# --- Composite grid --------------------------------------------------------

COMPOSITE_ROWS = 6
"""Art rows plus the one row the shadow is offset down by."""

COMPOSITE_COLS = 35
"""Art columns plus the one column the shadow is offset right by."""

MAIN = "main"
"""Composite cell tag for the accent layer."""

SHADOW = "shadow"
"""Composite cell tag for the offset layer beneath it."""

CompositeGrid = tuple[tuple["str | None", ...], ...]


def _build_composite() -> CompositeGrid:
    """Composite the shadow and main layers into one character grid.

    A terminal cannot overlay text, so both layers are resolved into a single
    grid before anything is printed.  The shadow is painted first at a
    one-down, one-right offset and the main layer is painted over it, so main
    always wins a collision rather than the two blending into mush.

    Returns:
        A :data:`COMPOSITE_ROWS` x :data:`COMPOSITE_COLS` grid whose cells are
        :data:`MAIN`, :data:`SHADOW`, or ``None`` for empty.
    """
    grid: list[list[str | None]] = [
        [None] * COMPOSITE_COLS for _ in range(COMPOSITE_ROWS)
    ]
    for row, line in enumerate(BANNER_ART):
        for col, char in enumerate(line):
            if char == BANNER_BLOCK:
                grid[row + 1][col + 1] = SHADOW
    for row, line in enumerate(BANNER_ART):
        for col, char in enumerate(line):
            if char == BANNER_BLOCK:
                grid[row][col] = MAIN
    return tuple(tuple(cells) for cells in grid)


BANNER_COMPOSITE: CompositeGrid = _build_composite()
"""The composited grid, built once at import rather than per invocation."""


# --- Small lockup ----------------------------------------------------------

SMALL_BANNER_NAME = "kaira"
"""Lowercase always — it is how the command is typed."""

SMALL_BANNER_RULE = "\u2500"
"""Box-drawing character the divider is built from."""

SMALL_BANNER_MAX_WIDTH = 80
"""Cap for the rule. A rule across a 200-column window reads as broken."""

SMALL_BANNER_MIN_RULE = 4
"""Below this the rule is dropped entirely rather than truncated."""


# --- Degradation ladder ----------------------------------------------------

SURFACE_LARGE = "large"
"""Surface asking for ceremony: ``kaira init``."""

SURFACE_SMALL = "small"
"""Surface asking for wayfinding: bare ``kaira``, ``--version``, ``about``,
``commands``."""

TIER_LARGE_SHADOW = 1
TIER_LARGE_FLAT = 2
TIER_SMALL = 3
TIER_PLAIN = 4

LARGE_BANNER_MIN_WIDTH = 44
"""Tier 1 floor: the 35-column composite, the 2-column indent, right margin."""

FLAT_BANNER_MIN_WIDTH = 40
"""Tier 2 floor. Below it the large lockup drops a tier rather than clipping."""

_TIER_CACHE: dict[str, int] = {}
_QUIET = False


def set_quiet(value: bool) -> None:
    """Record whether this invocation was asked to stay quiet.

    Set once per invocation from the root command group, before any parameter
    callback runs, so every banner surface sees the same answer no matter where
    ``--quiet`` appeared on the command line.
    """
    global _QUIET
    _QUIET = bool(value)


def is_quiet() -> bool:
    """Return True when banners must be suppressed for this invocation."""
    return _QUIET


def reset_banner_cache() -> None:
    """Drop the cached tier so the next invocation re-resolves the ladder."""
    _TIER_CACHE.clear()


def banner_width() -> int:
    """Return the width the banner lays itself out against.

    Read from Rich's console rather than :func:`terminal_width`, because Rich
    already resolves the non-TTY and redirected cases that decide whether block
    art is appropriate at all.
    """
    from kaira.console import console

    return console.size.width


def banner_is_terminal() -> bool:
    """Return True when banner output is headed for a real terminal.

    Taken from the same Rich console as :func:`banner_width` so the two cannot
    disagree: a redirected stream reporting a 200-column width is exactly the
    case that would otherwise dump block art into a log file.
    """
    from kaira.console import console

    return console.is_terminal


def resolve_banner_tier(surface: str) -> int:
    """Resolve which banner a surface gets — top to bottom, first match wins.

    The only place terminal width or capability is checked for banner purposes,
    and the result is cached for the invocation: a per-line width check is how
    a banner ends up disagreeing with itself halfway down.

    Args:
        surface: :data:`SURFACE_LARGE` or :data:`SURFACE_SMALL`.

    Returns:
        One of :data:`TIER_LARGE_SHADOW`, :data:`TIER_LARGE_FLAT`,
        :data:`TIER_SMALL`, :data:`TIER_PLAIN`.
    """
    cached = _TIER_CACHE.get(surface)
    if cached is not None:
        return cached
    tier = _resolve_banner_tier_uncached(surface)
    _TIER_CACHE[surface] = tier
    return tier


def _resolve_banner_tier_uncached(surface: str) -> int:
    """Evaluate the ladder. See :func:`resolve_banner_tier`."""
    # Tier 4 outranks every width question: without UTF-8 there is no block
    # art, no bolt and no rule left to degrade *to*.
    if not supports_utf8():
        return TIER_PLAIN

    # Piped or redirected output never gets block art — `kaira init > log.txt`
    # must produce a readable log, not 200 block characters.
    if surface == SURFACE_LARGE and banner_is_terminal():
        width = banner_width()
        if is_interactive() and width >= LARGE_BANNER_MIN_WIDTH:
            return TIER_LARGE_SHADOW
        # The shadow only reads as a shadow when colour separates it from the
        # main layer; without colour the two layers are the same glyph.
        if width >= FLAT_BANNER_MIN_WIDTH:
            return TIER_LARGE_FLAT

    return TIER_SMALL


# --- Renderable output -----------------------------------------------------


def _composite_row(cells: Sequence["str | None"]) -> "Text":
    """Render one composite grid row as a styled Rich ``Text``.

    Consecutive cells sharing a layer collapse into one span, so a single row
    can carry both accent and shadow runs.
    """
    from rich.text import Text

    styles = {MAIN: Theme.ACCENT_BANNER, SHADOW: Theme.ACCENT_BANNER_DIM}
    text = Text()
    for tag, group in itertools.groupby(cells):
        count = sum(1 for _ in group)
        if tag is None:
            text.append(" " * count)
        else:
            text.append(BANNER_BLOCK * count, style=styles[tag])
    text.rstrip()
    return text


def large_banner_lines(*, shadow: bool) -> list["Text"]:
    """Return the large lockup as styled lines, indented and ready to print.

    Args:
        shadow: True for the composited two-layer form (Tier 1), False for the
            flat main layer only (Tier 2).
    """
    from rich.text import Text

    if shadow:
        rows = [_composite_row(cells) for cells in BANNER_COMPOSITE]
    else:
        rows = [Text(line.rstrip(), style=Theme.ACCENT_BANNER) for line in BANNER_ART]

    lines: list[Text] = []
    for row in rows:
        line = Text(BANNER_INDENT)
        line.append_text(row)
        lines.append(line)
    return lines


def large_banner_tagline() -> "Text":
    """Return the indented, muted tagline shown under the large lockup."""
    from rich.text import Text

    return Text(f"{BANNER_INDENT}{BANNER_TAGLINE}", style=Theme.MUTED)


def small_banner_line(version: str | None) -> "Text":
    """Return the small lockup: mark, rule, and optional right-aligned version.

    The rule fills whatever is left between mark and version, which is what
    lets the small banner act as a divider rather than only a label.  It is
    measured in terminal cells rather than characters because the bolt is
    double-width: sizing by ``len`` would push the line one column past the
    right margin and wrap it, which is the one thing a rule must never do.

    Args:
        version: Version string without the ``v`` prefix, or ``None`` to omit
            the version and let the rule run to the right margin.
    """
    from rich.cells import cell_len
    from rich.text import Text

    mark = f"{Symbols.BOLT} {SMALL_BANNER_NAME}"
    version_text = f"v{version}" if version is not None else ""

    width = min(banner_width(), SMALL_BANNER_MAX_WIDTH)
    padding = 2 if version_text else 1
    rule_length = width - cell_len(mark) - cell_len(version_text) - padding

    text = Text()
    text.append(Symbols.BOLT, style=Theme.ACCENT_BANNER)
    text.append(" ")
    text.append(SMALL_BANNER_NAME, style=Theme.ACCENT_BANNER)

    # A one-character rule is worse than no rule, so it is dropped whole.
    if rule_length >= SMALL_BANNER_MIN_RULE:
        text.append(" ")
        text.append(SMALL_BANNER_RULE * rule_length, style=Theme.ACCENT_BANNER_DIM)

    if version_text:
        text.append(" ")
        text.append(version_text, style=Theme.MUTED)
    return text


def plain_banner_line(version: str) -> str:
    """Return the ASCII-only lockup used when UTF-8 is unavailable (Tier 4)."""
    return f"{SMALL_BANNER_NAME} v{version}"


# ---------------------------------------------------------------------------
# Theme — colour / style constants
# ---------------------------------------------------------------------------


class Theme:
    """Rich markup style strings used throughout Phase 5 commands."""

    PRIMARY = "bold cyan"
    SUCCESS = "bold green"
    WARNING = "bold yellow"
    ERROR = "bold red"
    MUTED = "grey58"
    ACCENT = "magenta"

    # Banner accent — one hue, two stops.  The dim stop is that hue
    # darkened, never a second colour: the shadow has to read as the same
    # ink in shade, not as a different mark sitting behind the first.
    ACCENT_BANNER = "#22D3EE"
    ACCENT_BANNER_DIM = "#0F5F6B"

    # Panel border styles
    BORDER_PRIMARY = "cyan"
    BORDER_SUCCESS = "green"
    BORDER_WARNING = "yellow"
    BORDER_ERROR = "red"


# ---------------------------------------------------------------------------
# Symbols — interactive (emoji) vs plain-text (CI) variants
# ---------------------------------------------------------------------------


class Symbols:
    """Terminal symbols that degrade to ASCII when not interactive.

    Access via :func:`get_symbols` rather than this class directly so the
    correct variant is returned based on the current runtime context.
    """

    # Interactive (emoji) set
    OK = "✅"
    FAIL = "❌"
    WARN = "⚠️"
    PENDING = "⏳"
    SKIP = "⏭️"
    BOLT = "⚡"
    ARROW = "→"
    POINTER = "❯"
    CLOUD = "☁️"
    LOCK = "🔒"
    SPINNER = "⠋"

    # Progress state symbols (Phase 7.5)
    PROGRESS_PENDING = "◌"
    PROGRESS_ACTIVE = "◐"
    PROGRESS_DONE = "✓"
    PROGRESS_PARTIAL = "!"
    PROGRESS_FAILED = "✗"

    # Plain-text (CI / NO_COLOR) fallbacks
    OK_PLAIN = "[ok]"
    FAIL_PLAIN = "[x]"
    WARN_PLAIN = "[!]"
    PENDING_PLAIN = "[~]"
    SKIP_PLAIN = "[>]"
    BOLT_PLAIN = "[*]"
    ARROW_PLAIN = "->"
    POINTER_PLAIN = ">"
    CLOUD_PLAIN = "[cloud]"
    LOCK_PLAIN = "[lock]"

    # Progress state plain-text fallbacks (Phase 7.5)
    PROGRESS_PENDING_PLAIN = "."
    PROGRESS_ACTIVE_PLAIN = ">"
    PROGRESS_DONE_PLAIN = "[ok]"
    PROGRESS_PARTIAL_PLAIN = "[!]"
    PROGRESS_FAILED_PLAIN = "[x]"


def sym(name: str) -> str:
    """Return the appropriate symbol for the current runtime context.

    Uses emoji when :func:`is_interactive` is True, otherwise returns the
    ``_PLAIN`` fallback.

    Args:
        name: Attribute name on :class:`Symbols` (e.g. ``"OK"``, ``"FAIL"``).

    Returns:
        The symbol string suitable for current output context.
    """
    interactive = is_interactive()
    value = getattr(Symbols, name, "?")
    if not interactive:
        plain = getattr(Symbols, f"{name}_PLAIN", value)
        return plain
    return value
