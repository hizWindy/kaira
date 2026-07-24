"""Kaira terminal design system — single source of truth for all Phase 5 UI.

All new Phase 5 commands must import from this module instead of defining
inline colours or symbols.  Phase 1–4 commands are left untouched.
"""

from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# Attribution — single source of truth (never hardcode per surface)
# ---------------------------------------------------------------------------

AUTHOR_NAME = "Khair"
AUTHOR_ARABIC = "خير"
PROJECT_URL = "github.com/khair/devflow"


def attribution() -> str:
    """Return the attribution line, UTF-8-gated with a Latin-only fallback."""
    if supports_utf8():
        return f"Created by {AUTHOR_NAME} · {AUTHOR_ARABIC}"
    return f"Created by {AUTHOR_NAME}"


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
