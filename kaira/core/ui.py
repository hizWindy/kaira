"""Kaira terminal UI helpers — panel, table, and footer utilities.

All new Phase 5 commands must use these helpers instead of hand-rolling Rich
layouts.  Phase 1–4 command output is left entirely untouched.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Sequence, TypeVar

from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from kaira.console import console
from kaira.core.progress import State, state_style, state_symbol
from kaira.core.theme import (
    GUTTER,
    LABEL_WIDTH,
    RULE_WIDTH,
    Theme,
    get_banner,
    is_interactive,
    sym,
    terminal_width,
)


F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Banner helper (Phase 7.5)
# ---------------------------------------------------------------------------


def render_banner() -> None:
    """Print the Kaira banner appropriate for the current terminal.

    Uses :func:`~kaira.core.theme.get_banner` for three-tier degradation.
    Called explicitly by entry-point surfaces — never from a global Typer
    callback.  The banner is a brand moment, not a working-command header.
    """
    from kaira import __version__

    banner = get_banner(__version__)
    if is_interactive():
        console.print(banner)
    else:
        console.print(banner, highlight=False)


# ---------------------------------------------------------------------------
# Section / step vocabulary
#
# Long-running commands read as a sequence of named sections, each a short list
# of steps that resolve to a final state.  Everything is laid out against one
# content column (Theme.RULE_WIDTH) inside one gutter, so the eye tracks a
# single left edge from the first line to the last.
# ---------------------------------------------------------------------------


def _symbol_cell(state: State) -> str:
    """Return the state symbol padded to a uniform column.

    ASCII fallbacks are not all the same width (``[ok]`` vs ``.``), so without
    padding the label column would shift from line to line in exactly the
    environments — CI logs, Windows consoles — where alignment is the only
    structure left.
    """
    raw = state_symbol(state)
    width = max(len(state_symbol(candidate)) for candidate in State)
    return escape(raw) + " " * (width - len(raw))


def _marker_width() -> int:
    """Width of the symbol column, including its trailing space."""
    return max(len(state_symbol(candidate)) for candidate in State) + 1


def _pad(label: str) -> str:
    """Escape *label* and pad it to the shared label column.

    A label longer than the column keeps a single trailing space, so an
    oversized label pushes its value right instead of running into it.
    """
    escaped = escape(label)
    if len(label) >= LABEL_WIDTH:
        return escaped
    return escaped + " " * (LABEL_WIDTH - len(label))


def rule() -> None:
    """Print a hairline rule at the shared content width."""
    char = "─" if is_interactive() else "-"
    width = min(RULE_WIDTH, max(terminal_width() - len(GUTTER) - 1, 8))
    console.print(f"{GUTTER}[{Theme.MUTED}]{char * width}[/{Theme.MUTED}]")


def section(title: str, note: str = "") -> None:
    """Open a section: a blank line, a lowercase title, then a hairline rule.

    Args:
        title: Section name (e.g. ``"scaffold"``).
        note: Optional muted annotation shown after the title.
    """
    heading = f"{GUTTER}[{Theme.PRIMARY}]{escape(title)}[/{Theme.PRIMARY}]"
    if note:
        heading += f" [{Theme.MUTED}]· {escape(note)}[/{Theme.MUTED}]"
    console.print()
    console.print(heading)
    rule()


def step(
    label: str,
    detail: str = "",
    state: State = State.DONE,
) -> None:
    """Print one step line: ``✓ label   detail``.

    The label is padded to a fixed column so details line up down the section,
    and the state symbol degrades to ASCII with the rest of the theme.

    Args:
        label: What the step did (e.g. ``"virtualenv"``).
        detail: Muted trailing facts (e.g. ``".venv · 2.4s"``).
        state: Outcome, driving both symbol and colour.
    """
    style = state_style(state)
    line = f"{GUTTER}[{style}]{_symbol_cell(state)}[/{style}] {_pad(label)}"
    if detail:
        line += f" [{Theme.MUTED}]{escape(detail)}[/{Theme.MUTED}]"
    console.print(line.rstrip())


def note(label: str, detail: str = "") -> None:
    """Print an observation line that makes no claim about success.

    Narration such as "server detected" or "driver not installed" is neither a
    completed step nor a failure — giving it a checkmark would overstate it and
    a pending symbol would misdescribe it, so it gets a neutral bullet and the
    verdict is left to the step line that follows.
    """
    bullet = ("·" if is_interactive() else "-").ljust(_marker_width() - 1)
    line = f"{GUTTER}[{Theme.MUTED}]{bullet}[/{Theme.MUTED}] {_pad(label)}"
    if detail:
        line += f" [{Theme.MUTED}]{escape(detail)}[/{Theme.MUTED}]"
    console.print(line.rstrip())


def subtext(text: str) -> None:
    """Print a muted continuation line under the previous step's value column."""
    # gutter + symbol column + label column + separator
    indent = GUTTER + " " * (_marker_width() + LABEL_WIDTH + 1)
    console.print(f"{indent}[{Theme.MUTED}]{escape(text)}[/{Theme.MUTED}]")


def field(label: str, value: str) -> None:
    """Print an aligned ``label   value`` pair with no state symbol.

    Used for settings the user chose or facts about the environment, which are
    not steps and should not wear a checkmark.
    """
    indent = GUTTER + " " * _marker_width()
    console.print(
        f"{indent}[{Theme.MUTED}]{_pad(label)}[/{Theme.MUTED}] {escape(value)}"
    )


def hint(command: str) -> None:
    """Print a muted, copy-pasteable next step: ``→ kaira run``."""
    arrow = escape(sym("ARROW"))
    console.print(f"{GUTTER}[{Theme.MUTED}]{arrow} {escape(command)}[/{Theme.MUTED}]")


# ---------------------------------------------------------------------------
# Panel helper
# ---------------------------------------------------------------------------


def panel(
    content: str,
    title: str,
    subtitle: str = "",
    border_style: str = Theme.BORDER_PRIMARY,
    expand: bool = False,
) -> None:
    """Print a rounded-border Rich panel with a standardised title format.

    Title is rendered as ``⚡ Kaira — <title>`` (or plain equivalent).
    Subtitle appears on the right side of the panel border.

    Args:
        content: Body text (Rich markup accepted).
        title: Short title shown on the left border (no markup prefix needed).
        subtitle: Optional right-side annotation (e.g. elapsed time, date).
        border_style: Rich colour/style for the border.
        expand: Whether the panel should expand to full width.
    """
    bolt = sym("BOLT")
    full_title = f"[{border_style}]{bolt} Kaira — {title}[/{border_style}]"
    rich_subtitle = f"[{Theme.MUTED}]{subtitle}[/{Theme.MUTED}]" if subtitle else ""
    console.print(
        Panel(
            content,
            title=full_title,
            subtitle=rich_subtitle,
            border_style=border_style,
            expand=expand,
        )
    )


# ---------------------------------------------------------------------------
# Key-value table helper
# ---------------------------------------------------------------------------


def kv_table(
    rows: Sequence[tuple[str, str]],
    title: str = "",
) -> None:
    """Print a two-column key → value grid.

    Keys are displayed in :attr:`Theme.MUTED` style; values are normal text.

    Args:
        rows: Sequence of ``(key, value)`` string pairs.
        title: Optional table title shown above.
    """
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=False,
        title=title or None,
        padding=(0, 1),
    )
    table.add_column("Key", style=Theme.MUTED, no_wrap=True)
    table.add_column("Value")
    for key, value in rows:
        table.add_row(key, value)
    console.print(table)


# ---------------------------------------------------------------------------
# Data table helper
# ---------------------------------------------------------------------------


def data_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    title: str = "",
    numeric_cols: Sequence[int] | None = None,
) -> None:
    """Print a Rich table with SIMPLE_HEAD box style and themed header.

    Args:
        headers: Column header names.
        rows: Data rows, each a sequence of string values matching *headers*.
        title: Optional table title.
        numeric_cols: Indices of numeric columns (right-aligned).
    """
    numeric_cols = numeric_cols or []
    table = Table(
        box=box.SIMPLE_HEAD,
        title=title or None,
        header_style=Theme.PRIMARY,
    )
    for i, hdr in enumerate(headers):
        justify: Any = "right" if i in numeric_cols else "left"
        table.add_column(hdr, justify=justify)
    for row in rows:
        table.add_row(*row)
    console.print(table)


# ---------------------------------------------------------------------------
# Footer helpers
# ---------------------------------------------------------------------------

_RULE_STYLE = "dim"


def success_footer(
    message: str,
    elapsed_s: float | None = None,
    files: int | None = None,
    warnings: int = 0,
) -> None:
    """Print a standardised success footer line.

    Format::

        ────────────────────────────────────────────────
        ✅ Done in 1.4s · 5 files generated · 0 warnings

    Args:
        message: Short success description (replaces "Done").
        elapsed_s: Elapsed time in seconds; omitted when ``None``.
        files: Number of files generated; omitted when ``None``.
        warnings: Warning count; shown when non-zero.
    """
    console.rule(style=_RULE_STYLE)
    ok = sym("OK")
    parts: list[str] = [f"[{Theme.SUCCESS}]{ok} {message}[/{Theme.SUCCESS}]"]
    if elapsed_s is not None:
        elapsed_str = (
            f"{elapsed_s:.1f}s" if elapsed_s >= 1 else f"{int(elapsed_s * 1000)}ms"
        )
        parts.append(f"[{Theme.MUTED}]in {elapsed_str}[/{Theme.MUTED}]")
    if files is not None:
        parts.append(
            f"[{Theme.MUTED}]{files} file{'s' if files != 1 else ''} generated[/{Theme.MUTED}]"
        )
    if warnings:
        parts.append(
            f"[{Theme.WARNING}]{warnings} warning{'s' if warnings != 1 else ''}[/{Theme.WARNING}]"
        )
    else:
        parts.append(f"[{Theme.MUTED}]0 warnings[/{Theme.MUTED}]")
    console.print(" · ".join(parts))


def error_footer(message: str, hint: str = "") -> None:
    """Print a standardised error footer line.

    Args:
        message: Short error description.
        hint: Optional hint shown after the message.
    """
    console.rule(style=_RULE_STYLE)
    fail = sym("FAIL")
    text = f"[{Theme.ERROR}]{fail} {message}[/{Theme.ERROR}]"
    if hint:
        text += f"  [{Theme.MUTED}]→ {hint}[/{Theme.MUTED}]"
    console.print(text)


# ---------------------------------------------------------------------------
# @with_summary timing decorator
# ---------------------------------------------------------------------------


def with_summary(fn: F) -> F:
    """Decorator that wraps a Phase 5 command with a timing footer.

    After the decorated function returns, prints::

        ✅ Done in 1.4s · 0 warnings

    The decorated function may raise :class:`SystemExit` or
    :class:`typer.Exit` — these are re-raised after printing the footer.

    Args:
        fn: Typer command function to wrap.

    Returns:
        Wrapped function with identical signature.

    Example::

        @app.command("connect")
        @with_summary
        def cloud_connect() -> None:
            ...
    """
    import typer  # local import to avoid circular at module level

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        exit_exc: BaseException | None = None
        result: Any = None
        try:
            result = fn(*args, **kwargs)
        except (SystemExit, typer.Exit) as exc:
            exit_exc = exc
        finally:
            elapsed = time.perf_counter() - start
            success_footer("Done", elapsed_s=elapsed)
        if exit_exc is not None:
            raise exit_exc
        return result

    return _wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Spinner context manager helper
# ---------------------------------------------------------------------------


def spinner_context(message: str) -> Any:
    """Return a Rich status context for indeterminate waits.

    In non-interactive mode returns a no-op context manager that prints
    ``... <message>`` on enter.

    Args:
        message: Text shown next to the spinner.

    Returns:
        A context manager compatible with ``with`` statements.
    """
    if is_interactive():
        return console.status(
            f"[{Theme.MUTED}]{message}[/{Theme.MUTED}]", spinner="dots"
        )
    return _PlainStatus(message)


class _PlainStatus:
    """Fallback no-op context manager for non-TTY environments."""

    def __init__(self, message: str) -> None:
        self._message = message

    def __enter__(self) -> "_PlainStatus":
        console.print(f"... {self._message}")
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def update(self, message: str) -> None:  # noqa: D102
        console.print(f"... {message}")
