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
    METER_MIN_WIDTH,
    METER_WIDTH,
    RULE_WIDTH,
    SURFACE_LARGE,
    SURFACE_SMALL,
    TIER_LARGE_FLAT,
    TIER_LARGE_SHADOW,
    TIER_PLAIN,
    Theme,
    is_interactive,
    is_quiet,
    large_banner_lines,
    large_banner_tagline,
    plain_banner_line,
    resolve_banner_tier,
    small_banner_line,
    small_banner_sweep,
    sym,
    terminal_width,
)


F = TypeVar("F", bound=Callable[..., Any])


# ---------------------------------------------------------------------------
# Banner surfaces
#
# Two functions, one call site each.  A banner printed twice in one invocation
# is a bug, so no command may reach past these into the theme layer.
# ---------------------------------------------------------------------------


def render_large_banner() -> None:
    """Print the large block lockup. ``kaira init`` only.

    Degrades through :func:`~kaira.core.theme.resolve_banner_tier`: the
    shadowed composite in a wide colour terminal, the flat main layer without
    colour, and the small lockup or the plain line when the terminal cannot
    carry block art at all.  A narrow terminal drops a tier rather than getting
    a clipped banner.

    The rows are handed to :func:`~kaira.core.motion.reveal`, so in a live
    terminal the lockup draws itself in from the top and everywhere else prints
    exactly the same lines at once.
    """
    from kaira import __version__
    from kaira.core import motion

    if is_quiet():
        return

    tier = resolve_banner_tier(SURFACE_LARGE)
    if tier == TIER_PLAIN:
        console.print(plain_banner_line(__version__), highlight=False)
        return
    if tier not in (TIER_LARGE_SHADOW, TIER_LARGE_FLAT):
        console.print(small_banner_line(__version__))
        return

    console.print()
    motion.reveal(large_banner_lines(shadow=tier == TIER_LARGE_SHADOW))
    console.print()
    console.print(large_banner_tagline())
    console.print()


def render_small_banner(*, show_version: bool = True, animate: bool = False) -> None:
    """Print the small lockup: bare ``kaira``, ``--version``, ``about``, ``commands``.

    Args:
        show_version: False on surfaces that already state the version in their
            body, where repeating it would only shorten the rule.
        animate: True on arrival surfaces, where a sweep along the rule is
            ceremony.  Left False for ``--version`` and the like: those are
            read by scripts and by people in a hurry, and neither wants the
            mark to take a beat before the answer.
    """
    from kaira import __version__
    from kaira.core import motion

    if is_quiet():
        return

    if resolve_banner_tier(SURFACE_SMALL) == TIER_PLAIN:
        console.print(plain_banner_line(__version__), highlight=False)
        return

    version = __version__ if show_version else None
    line = small_banner_line(version)
    if animate:
        motion.play(small_banner_sweep(version), line)
        return
    console.print(line)


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


# Each element of the vocabulary comes in two halves: an ``fmt_*`` function
# that returns the markup and a same-named function that prints it.  Surfaces
# that animate (see :mod:`kaira.core.motion`) have to compose their whole block
# before any of it reaches the screen, and duplicating the layout rules to do
# that is how two surfaces end up disagreeing about where the value column is.


def fmt_rule() -> str:
    """Return a hairline rule at the shared content width."""
    char = "─" if is_interactive() else "-"
    width = min(RULE_WIDTH, max(terminal_width() - len(GUTTER) - 1, 8))
    return f"{GUTTER}[{Theme.MUTED}]{char * width}[/{Theme.MUTED}]"


def rule() -> None:
    """Print a hairline rule at the shared content width."""
    console.print(fmt_rule())


def fmt_section(title: str, note: str = "") -> list[str]:
    """Return a section opener: a blank line, a lowercase title, a rule.

    Args:
        title: Section name (e.g. ``"scaffold"``).
        note: Optional muted annotation shown after the title.
    """
    heading = f"{GUTTER}[{Theme.PRIMARY}]{escape(title)}[/{Theme.PRIMARY}]"
    if note:
        heading += f" [{Theme.MUTED}]· {escape(note)}[/{Theme.MUTED}]"
    return ["", heading, fmt_rule()]


def section(title: str, note: str = "") -> None:
    """Open a section: a blank line, a lowercase title, then a hairline rule.

    Args:
        title: Section name (e.g. ``"scaffold"``).
        note: Optional muted annotation shown after the title.
    """
    for line in fmt_section(title, note):
        console.print(line)


def fmt_step(label: str, detail: str = "", state: State = State.DONE) -> str:
    """Return one step line: ``✓ label   detail``.

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
    return line.rstrip()


def step(
    label: str,
    detail: str = "",
    state: State = State.DONE,
) -> None:
    """Print one step line: ``✓ label   detail``."""
    console.print(fmt_step(label, detail, state))


def fmt_note(label: str, detail: str = "") -> str:
    """Return an observation line that makes no claim about success.

    Narration such as "server detected" or "driver not installed" is neither a
    completed step nor a failure — giving it a checkmark would overstate it and
    a pending symbol would misdescribe it, so it gets a neutral bullet and the
    verdict is left to the step line that follows.
    """
    bullet = ("·" if is_interactive() else "-").ljust(_marker_width() - 1)
    line = f"{GUTTER}[{Theme.MUTED}]{bullet}[/{Theme.MUTED}] {_pad(label)}"
    if detail:
        line += f" [{Theme.MUTED}]{escape(detail)}[/{Theme.MUTED}]"
    return line.rstrip()


def note(label: str, detail: str = "") -> None:
    """Print an observation line that makes no claim about success."""
    console.print(fmt_note(label, detail))


def fmt_subtext(text: str) -> str:
    """Return a muted continuation line under the previous step's value column."""
    # gutter + symbol column + label column + separator
    indent = GUTTER + " " * (_marker_width() + LABEL_WIDTH + 1)
    return f"{indent}[{Theme.MUTED}]{escape(text)}[/{Theme.MUTED}]"


def subtext(text: str) -> None:
    """Print a muted continuation line under the previous step's value column."""
    console.print(fmt_subtext(text))


def fmt_field(label: str, value: str) -> str:
    """Return an aligned ``label   value`` pair with no state symbol.

    Used for settings the user chose or facts about the environment, which are
    not steps and should not wear a checkmark.
    """
    indent = GUTTER + " " * _marker_width()
    return f"{indent}[{Theme.MUTED}]{_pad(label)}[/{Theme.MUTED}] {escape(value)}"


def field(label: str, value: str) -> None:
    """Print an aligned ``label   value`` pair with no state symbol."""
    console.print(fmt_field(label, value))


def fmt_hint(command: str) -> str:
    """Return a muted, copy-pasteable next step: ``→ kaira run``."""
    arrow = escape(sym("ARROW"))
    return f"{GUTTER}[{Theme.MUTED}]{arrow} {escape(command)}[/{Theme.MUTED}]"


def hint(command: str) -> None:
    """Print a muted, copy-pasteable next step: ``→ kaira run``."""
    console.print(fmt_hint(command))


# ---------------------------------------------------------------------------
# Overview vocabulary
#
# Three elements for surfaces the user *lands* on rather than reads through: a
# heading that names the thing and states its condition, a meter that answers
# "how far along is this" without counting lines, and a stat row that puts
# small numbers side by side instead of one per line.  All three lay out
# against the same content column as the step vocabulary above.
# ---------------------------------------------------------------------------


def fmt_pill(label: str, state: State = State.DONE, *, filled: bool = True) -> str:
    """Return a coloured status dot with its label: ``● online``.

    A pill reports a condition, where a step reports an outcome.  "online" is
    not something that succeeded, so it gets a dot rather than a checkmark and
    takes its colour — not its shape — from the state.

    Args:
        label: Short condition, lowercase (e.g. ``"online"``).
        state: Drives the colour only.
        filled: False for a hollow dot, for conditions that are absent rather
            than bad (nothing configured yet).
    """
    dot = escape(sym("DOT" if filled else "DOT_OPEN"))
    style = state_style(state)
    return f"[{style}]{dot} {escape(label)}[/{style}]"


def fmt_headline(title: str, badge: str = "") -> str:
    """Return a heading with *title* left and *badge* pushed to the right margin.

    Args:
        title: The subject, printed prominently (e.g. the project name).
        badge: Pre-styled markup, usually from :func:`fmt_pill`, right-aligned
            against the shared content width.  Dropped when the terminal is too
            narrow to separate the two, rather than wrapped onto its own line.
    """
    from rich.cells import cell_len
    from rich.text import Text

    head = f"{GUTTER}[bold]{escape(title)}[/bold]"
    if not badge:
        return head

    width = min(RULE_WIDTH, max(terminal_width() - len(GUTTER) - 1, 8))
    badge_width = cell_len(Text.from_markup(badge).plain)
    padding = width - cell_len(title) - badge_width
    if padding < 2:
        return head
    return f"{head}{' ' * padding}{badge}"


def fmt_caption(text: str) -> str:
    """Return a muted line at the gutter, for the subtitle under a headline.

    Unlike :func:`fmt_subtext` this sits at the left edge rather than under the
    value column: it qualifies the whole heading, not one step's outcome.
    """
    return f"{GUTTER}[{Theme.MUTED}]{escape(text)}[/{Theme.MUTED}]"


def caption(text: str) -> None:
    """Print a muted line at the gutter, under a headline."""
    console.print(fmt_caption(text))


def _content_width() -> int:
    """Return the width one line of body content has to work with."""
    return min(RULE_WIDTH, max(terminal_width() - len(GUTTER) - 1, 8))


def fmt_meter(done: int, total: int, label: str = "") -> str:
    """Return a filled bar with its fraction: ``ready  ████░░░░  3/5``.

    The bar is the part that gives: it shrinks to whatever the terminal leaves
    after the label and the fraction, because a meter that wraps onto a second
    line has lost the one thing it was for — being read in a glance.

    Args:
        done: Completed count.
        total: Total count; a zero total renders an empty bar rather than
            dividing by it.
        label: Short leading label, padded to the shared label column.
    """
    full = sym("METER_FULL")
    empty = sym("METER_EMPTY")
    fraction = f"{done}/{total}"

    indent = GUTTER + " " * _marker_width()
    head_width = len(indent) + (max(len(label), LABEL_WIDTH) + 1 if label else 0)
    room = _content_width() + len(GUTTER) - head_width - len(fraction) - 1
    width = max(METER_MIN_WIDTH, min(METER_WIDTH, room))

    filled = int(width * done / total) if total > 0 else 0
    filled = max(0, min(filled, width))
    style = Theme.SUCCESS if total and done >= total else Theme.PRIMARY

    bar = (
        f"[{style}]{full * filled}[/{style}]"
        f"[{Theme.MUTED}]{empty * (width - filled)}[/{Theme.MUTED}]"
    )
    head = f"{indent}[{Theme.MUTED}]{_pad(label)}[/{Theme.MUTED}] " if label else indent
    return f"{head}{bar} [{Theme.MUTED}]{fraction}[/{Theme.MUTED}]"


#: Separators tried in order, widest first, until the stat row fits the line.
_STAT_SEPARATORS = ("   ·   ", "  ·  ", "  ")


def fmt_stats(pairs: Sequence[tuple[str, str]]) -> str:
    """Return small counts on one line: ``models  3   routers  3   tests  1``.

    The separator tightens rather than the row wrapping: numbers side by side
    are only easier to compare than stacked ones while they stay on one line.

    Args:
        pairs: ``(label, value)`` pairs, kept short — this row is for numbers
            that are quicker to compare beside each other than stacked.
    """
    indent = GUTTER + " " * _marker_width()
    cells = [f"{label} {value}" for label, value in pairs]
    limit = _content_width() + len(GUTTER)

    separator = _STAT_SEPARATORS[-1]
    for candidate in _STAT_SEPARATORS:
        if len(indent) + len(candidate.join(cells)) <= limit:
            separator = candidate
            break

    rendered = [
        f"[{Theme.MUTED}]{escape(label)}[/{Theme.MUTED}] {escape(value)}"
        for label, value in pairs
    ]
    return indent + f"[{Theme.MUTED}]{separator}[/{Theme.MUTED}]".join(rendered)


def headline(title: str, badge: str = "") -> None:
    """Print a heading with *title* left and *badge* at the right margin."""
    console.print(fmt_headline(title, badge))


def meter(done: int, total: int, label: str = "") -> None:
    """Print a filled bar with its fraction."""
    console.print(fmt_meter(done, total, label))


def stats(pairs: Sequence[tuple[str, str]]) -> None:
    """Print small counts side by side on one line."""
    console.print(fmt_stats(pairs))


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

    Title is rendered as ``⚡ Khaira — <title>`` (or plain equivalent).
    Subtitle appears on the right side of the panel border.

    Args:
        content: Body text (Rich markup accepted).
        title: Short title shown on the left border (no markup prefix needed).
        subtitle: Optional right-side annotation (e.g. elapsed time, date).
        border_style: Rich colour/style for the border.
        expand: Whether the panel should expand to full width.
    """
    bolt = sym("BOLT")
    full_title = f"[{border_style}]{bolt} Khaira — {title}[/{border_style}]"
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


# ---------------------------------------------------------------------------
# Command alias resolution echo and shortcuts table helpers
# ---------------------------------------------------------------------------


def _format_echo_tokens(tokens: list[str]) -> list[str]:
    """Format CLI tokens for echo display, masking sensitive values using Phase 4 helper."""
    from kaira.commands.ux_helpers import redact_sensitive

    formatted: list[str] = []
    skip_next = False
    for i, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue

        if token.startswith("--") and "=" in token:
            key, val = token[2:].split("=", 1)
            masked_val = redact_sensitive(key, val)
            if " " in masked_val and not (
                masked_val.startswith('"') or masked_val.startswith("'")
            ):
                masked_val = f'"{masked_val}"'
            formatted.append(f"--{key}={masked_val}")
        elif token.startswith("-"):
            key = token.lstrip("-")
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                val = tokens[i + 1]
                masked_val = redact_sensitive(key, val)
                formatted.append(token)
                if " " in masked_val and not (
                    masked_val.startswith('"') or masked_val.startswith("'")
                ):
                    masked_val = f'"{masked_val}"'
                formatted.append(masked_val)
                skip_next = True
            else:
                formatted.append(token)
        else:
            if " " in token and not (token.startswith('"') or token.startswith("'")):
                formatted.append(f'"{token}"')
            else:
                formatted.append(token)
    return formatted


def render_resolution_echo(tokens: list[str]) -> None:
    """Print one muted line showing the resolved long form before execution.

    Suppressed under --quiet and on non-TTY output.
    """
    from kaira.core.theme import is_interactive, is_quiet

    # Check quiet flag (from Theme or raw arguments)
    if is_quiet() or any(t in ("--quiet", "-q") for t in tokens):
        return

    # Check non-TTY / non-interactive output
    if not is_interactive():
        return

    formatted_tokens = _format_echo_tokens(tokens)
    arrow = sym("ARROW")
    cmd_str = " ".join(formatted_tokens)
    console.print(f"[{Theme.MUTED}]{arrow} kaira {cmd_str}[/{Theme.MUTED}]")


def render_shortcuts_table() -> None:
    """Render the ⚡ Shortcuts block at the bottom of kaira commands via data_table()."""
    rows = [
        ["g", "generate model", "mm", "migrate make"],
        ["gb", "generate bulk", "mr", "migrate run"],
        ["sm", "sync model", "st", "status"],
        ["up", "docker up", "q", "quality"],
        ["dn", "docker down", "t", "test run"],
        ["ds", "docker status", "?", "menu"],
    ]
    bolt = sym("BOLT")
    data_table(
        ["Alias", "Expands to", "Alias", "Expands to"],
        rows,
        title=f"{bolt} Shortcuts",
    )
    console.print(
        f"  [{Theme.MUTED}]Shortcuts are optional. Full commands always work.[/{Theme.MUTED}]"
    )
    console.print(
        f"  [{Theme.MUTED}]Tab-completion: kaira --install-completion[/{Theme.MUTED}]"
    )
