"""Kaira terminal design system — single source of truth for all UI.

All new commands must import from this module instead of defining
inline colours or symbols.  Contains the banner lockup, progress state
symbols, and the three-tier degradation system.
"""

from __future__ import annotations

import os
import shutil
import sys


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
# Banner lockup — single constant, never duplicated per surface
# ---------------------------------------------------------------------------

_BANNER_WORDMARK = (
    "\u2588 \u2588 \u2584\u2580\u2588 \u2588 \u2588\u2580\u2588 \u2584\u2580\u2588\n"
    "\u2588\u2580\u2584 \u2588\u2580\u2588 \u2588 \u2588\u2580\u2584 \u2588\u2580\u2588"
)
"""Two-line block wordmark (raw, unindented, no flanks). ~17 columns wide."""

_BANNER_GEAR = "\u2699\ufe0f"
"""Left flank: the automation gear. Occupies the wordmark indent on line 2."""

_BANNER_BOLT = "\u26a1"
"""Right flank: the bolt."""

_BANNER_INDENT = "   "
"""Wordmark indent. Matches the columns ``\u2699\ufe0f `` occupies on line 2, which is
what gives lines 1, 2 and the tagline a shared left edge."""

_BANNER_TAGLINE = "continuous scaffolding"
"""Tagline shown below the wordmark in muted style."""

_BANNER_PLAIN_TAGLINE = "continuous model-level FastAPI scaffolding"
"""Tagline used by the single-line plain fallback."""

BANNER_MIN_WIDTH = 32
"""Below this terminal width the wordmark wraps, so collapse to plain."""


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


def get_banner(version: str) -> str:
    """Return the Kaira banner string appropriate for the current terminal.

    Three tiers:

    1. **Full** — interactive TTY, UTF-8, colour: block wordmark with emoji
       flanks (\u2699\ufe0f left, \u26a1 right), version + tagline in muted style.
    2. **NO_COLOR** — UTF-8 but ``NO_COLOR`` set: same block wordmark with
       emoji flanks, no ANSI colour codes.
    3. **Plain** — non-TTY, non-UTF-8, piped/CI, or terminal < 32 columns:
       single line ``KAIRA v{version} \u00b7 continuous model-level FastAPI scaffolding``.

    Args:
        version: Version string (e.g. ``"0.1.0"``).

    Returns:
        The ready-to-print banner string (no trailing newline).
    """
    tty = sys.stdout.isatty()
    utf8 = supports_utf8()
    no_color = bool(os.environ.get("NO_COLOR"))
    width = terminal_width()

    # Tier 3: plain single line
    if not tty or not utf8 or width < BANNER_MIN_WIDTH:
        return f"KAIRA v{version} \u00b7 {_BANNER_PLAIN_TAGLINE}"

    # The wordmark is indented; line 2's gear flank occupies exactly those
    # columns, which is what gives all three lines a shared left edge.
    top, bottom = _BANNER_WORDMARK.splitlines()
    line1 = f"{_BANNER_INDENT}{top}"
    line2 = f"{_BANNER_GEAR} {bottom} {_BANNER_BOLT}"
    tagline = f"{_BANNER_INDENT}v{version} \u00b7 {_BANNER_TAGLINE}"

    # Tier 2: NO_COLOR — wordmark with emoji, no ANSI
    if no_color:
        return f"{line1}\n{line2}\n{tagline}"

    # Tier 1: full colour
    return (
        f"[{Theme.PRIMARY}]{line1}[/{Theme.PRIMARY}]\n"
        f"{_BANNER_GEAR} [{Theme.PRIMARY}]{bottom}[/{Theme.PRIMARY}] {_BANNER_BOLT}\n"
        f"[{Theme.MUTED}]{tagline}[/{Theme.MUTED}]"
    )


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
