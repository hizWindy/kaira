"""Kaira shared multi-step progress renderer (Phase 7.5).

Owns the phase/item state language used by installs, generation, and any
other batched operation.  Two-level model: an *operation* has ordered
*phases*; a phase may have nested *items*.

The renderer has two modes, selected automatically:

* **Interactive** — a live block repainted in place.  Every phase is visible
  from the start in its pending state, nested items appear under the
  currently active phase, and the block is erased on completion so no
  spinner frame is ever left on screen.
* **Plain** — under ``NO_COLOR``, non-TTY, non-UTF-8, or CI: no animation, no
  repainting, no cursor control codes.  One line per phase as it resolves,
  then the summary.

All symbols and styles resolve through :mod:`kaira.core.theme`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from types import TracebackType
from typing import Optional, Sequence

from rich.console import Group
from rich.live import Live
from rich.markup import escape
from rich.text import Text

from kaira.console import console
from kaira.core.theme import (
    GUTTER,
    RULE_WIDTH,
    Theme,
    is_interactive,
    sym,
    terminal_width,
)


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class State(Enum):
    """Progress state for phases and items."""

    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    PARTIAL = "partial"  # phase finished with some failed items
    FAILED = "failed"


#: States that mean "this phase/item will not change again".
_RESOLVED_STATES = (State.DONE, State.PARTIAL, State.FAILED)


# ---------------------------------------------------------------------------
# Symbol + style resolution
# ---------------------------------------------------------------------------

_STATE_SYMBOL_MAP: dict[State, str] = {
    State.PENDING: "PROGRESS_PENDING",
    State.ACTIVE: "PROGRESS_ACTIVE",
    State.DONE: "PROGRESS_DONE",
    State.PARTIAL: "PROGRESS_PARTIAL",
    State.FAILED: "PROGRESS_FAILED",
}

_STATE_STYLE_MAP: dict[State, str] = {
    State.PENDING: Theme.MUTED,
    State.ACTIVE: Theme.WARNING,
    State.DONE: Theme.SUCCESS,
    State.PARTIAL: Theme.WARNING,
    State.FAILED: Theme.ERROR,
}


def state_symbol(state: State) -> str:
    """Return the symbol for *state*, degraded via :func:`sym`."""
    return sym(_STATE_SYMBOL_MAP[state])


def state_style(state: State) -> str:
    """Return the Rich style string for *state*."""
    return _STATE_STYLE_MAP[state]


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

MAX_VISIBLE_ROWS = 6
"""Fixed height of the nested item block, including the ``+N more`` row."""

_BAR_WIDTH = 24
"""Width of the summary progress bar."""

_REFRESH_HZ = 8
"""Live repaint frequency.  High enough to feel live, low enough to be cheap."""

_PHASE_NAME_WIDTH = 10
"""Column width the phase name is padded to, so summaries line up."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ProgressItem:
    """A single item within a progress phase."""

    name: str
    state: State = State.PENDING
    elapsed_s: float = 0.0
    detail: str = ""
    version: str = ""
    _start: float = 0.0

    def start(self) -> None:
        """Mark this item as active and begin timing."""
        self.state = State.ACTIVE
        self._start = time.monotonic()

    def done(self, version: str = "", detail: str = "") -> None:
        """Mark this item as done and record elapsed time."""
        self.state = State.DONE
        self.elapsed_s = time.monotonic() - self._start if self._start else 0.0
        if version:
            self.version = version
        if detail:
            self.detail = detail

    def fail(self, reason: str = "") -> None:
        """Mark this item as failed with an optional short reason."""
        self.state = State.FAILED
        self.elapsed_s = time.monotonic() - self._start if self._start else 0.0
        self.detail = reason or "failed"


@dataclass
class ProgressPhase:
    """A phase within a multi-step operation."""

    name: str
    items: list[ProgressItem] = field(default_factory=list)
    state: State = State.PENDING
    elapsed_s: float = 0.0
    summary: str = ""
    _start: float = 0.0

    def start(self) -> None:
        """Mark this phase as active and begin timing."""
        self.state = State.ACTIVE
        self._start = time.monotonic()

    def finish(self, summary: str = "") -> None:
        """Mark this phase resolved, deriving the state from its items.

        A phase with no failed items is DONE; a phase where every item failed
        is FAILED; anything in between is PARTIAL.

        Args:
            summary: Optional summary text shown next to the phase name.
        """
        self.elapsed_s = time.monotonic() - self._start if self._start else 0.0
        if summary:
            self.summary = summary
        failed = [i for i in self.items if i.state == State.FAILED]
        if failed:
            self.state = (
                State.FAILED if len(failed) == len(self.items) else State.PARTIAL
            )
        else:
            self.state = State.DONE

    def fail(self, reason: str = "") -> None:
        """Mark the entire phase as failed."""
        self.elapsed_s = time.monotonic() - self._start if self._start else 0.0
        self.state = State.FAILED
        self.summary = reason


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-readable string (``340ms`` / ``2.1s``)."""
    if seconds < 1.0:
        return f"{int(seconds * 1000)}ms"
    return f"{seconds:.1f}s"


def format_size(size_bytes: float) -> str:
    """Format a byte count as a human-readable size."""
    if size_bytes < 1024:
        return f"{int(size_bytes)} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


class _LiveView:
    """Adapter making a :class:`ProgressRenderer` repaint on every Live tick."""

    def __init__(self, renderer: ProgressRenderer) -> None:
        self._renderer = renderer

    def __rich__(self) -> Group:
        """Return the current live block (recomputed on each refresh)."""
        return self._renderer.live_group()


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class ProgressRenderer:
    """Shared multi-step progress renderer.

    Usage::

        with ProgressRenderer("installing", strategy="uv", total=12,
                              phases=[resolve, download, install]) as r:
            resolve.start()
            r.refresh()
            ...
        r.print_result(fix_hints)

    Args:
        title: Operation title (e.g. ``"installing"``).
        strategy: Strategy label shown in the header (e.g. ``"uv"``).
        total: Total item count used by the progress bar.
        phases: Ordered list of phases, all visible from the start.
        unit: Noun for the item count in the header (e.g. ``"packages"``).
    """

    def __init__(
        self,
        title: str,
        strategy: str = "",
        total: int = 0,
        phases: Sequence[ProgressPhase] | None = None,
        unit: str = "packages",
    ) -> None:
        self.title = title
        self.strategy = strategy
        self.total = total
        self.unit = unit
        self.phases: list[ProgressPhase] = list(phases) if phases else []
        self._start = time.monotonic()
        self._live: Optional[Live] = None
        self._plain_emitted: set[int] = set()

    # -- Lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Begin rendering: open the live block, or print the plain header."""
        self._start = time.monotonic()
        if is_interactive():
            self._live = Live(
                _LiveView(self),
                console=console,
                refresh_per_second=_REFRESH_HZ,
                transient=True,
            )
            self._live.start()
        else:
            console.print(self._plain_header(), markup=False, highlight=False)

    def refresh(self) -> None:
        """Signal that state changed.

        Repaints the live block, or — in plain mode — emits a line for any
        phase that has resolved since the last call.
        """
        if self._live is not None:
            self._live.refresh()
        else:
            self._emit_plain_transitions()

    def stop(self) -> None:
        """Close the live block, erasing it so no active frame survives."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        else:
            self._emit_plain_transitions()

    def __enter__(self) -> ProgressRenderer:
        """Enter the rendering context."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Leave the rendering context, always closing the live block."""
        self.stop()

    # -- Rendering helpers ---------------------------------------------------

    def _header_text(self) -> str:
        """Build the header line: ``⚡ title · strategy · N packages``."""
        bolt = sym("BOLT")
        parts = [f"{bolt} {escape(self.title)}"]
        if self.strategy:
            parts.append(f" · {escape(self.strategy)}")
        if self.total:
            parts.append(f" · {self.total} {escape(self.unit)}")
        return f"{GUTTER}[{Theme.PRIMARY}]{''.join(parts)}[/{Theme.PRIMARY}]"

    def _plain_header(self) -> str:
        """Build the plain-text header used in non-interactive mode."""
        parts = [GUTTER, self.title]
        if self.strategy:
            parts.append(f" · {self.strategy}")
        if self.total:
            parts.append(f" · {self.total} {self.unit}")
        return "".join(parts)

    def _rule(self) -> str:
        """Return a thin horizontal rule, clamped to the terminal width."""
        width = min(RULE_WIDTH, max(terminal_width() - len(GUTTER) - 1, 8))
        char = "─" if is_interactive() else "-"
        return f"{GUTTER}[{Theme.MUTED}]{char * width}[/{Theme.MUTED}]"

    def _phase_line(self, phase: ProgressPhase) -> str:
        """Render a single phase summary line."""
        symbol = state_symbol(phase.state)
        style = state_style(phase.state)
        name = escape(phase.name)
        pad = " " * max(_PHASE_NAME_WIDTH - len(phase.name), 1)
        line = f"{GUTTER}[{style}]{symbol}[/{style}] {name}"

        details: list[str] = []
        if phase.summary:
            details.append(escape(phase.summary))
        if phase.elapsed_s and phase.state in _RESOLVED_STATES:
            details.append(format_elapsed(phase.elapsed_s))
        if details:
            line += f"{pad}[{Theme.MUTED}]{' · '.join(details)}[/{Theme.MUTED}]"
        return line

    def _item_line(self, item: ProgressItem) -> str:
        """Render a single nested item line."""
        symbol = state_symbol(item.state)
        style = state_style(item.state)
        line = f"{GUTTER}  [{style}]{symbol}[/{style}] {escape(item.name)}"
        if item.version:
            line += f" [{Theme.MUTED}]{escape(item.version)}[/{Theme.MUTED}]"
        elif item.detail and item.state != State.FAILED:
            line += f" [{Theme.MUTED}]{escape(item.detail)}[/{Theme.MUTED}]"
        return line

    def visible_items(self, phase: ProgressPhase) -> tuple[list[ProgressItem], int]:
        """Return ``(visible_items, hidden_count)`` for *phase*.

        The block height is fixed at :data:`MAX_VISIBLE_ROWS` rows regardless
        of how many packages the operation pulls.  The window keeps active and
        recently-resolved items visible in their original order; trailing
        pending items are what get folded into ``+N more``.
        """
        items = phase.items
        if len(items) <= MAX_VISIBLE_ROWS:
            return list(items), 0

        # One row is spent on the "+N more" line.
        window = MAX_VISIBLE_ROWS - 1

        frontier = 0
        for index, item in enumerate(items):
            if item.state in (State.ACTIVE, *_RESOLVED_STATES):
                frontier = index + 1
        start = max(0, min(frontier - window + 1, len(items) - window))
        visible = items[start : start + window]
        return visible, len(items) - len(visible)

    def _progress_bar(self) -> str:
        """Render the bar line: ``████░░░░  6/12  4.8s``."""
        done_count = sum(
            1
            for phase in self.phases
            for item in phase.items
            if item.state in (State.DONE, State.FAILED)
        )
        total = self.total or max(sum(len(p.items) for p in self.phases), 1)
        elapsed = format_elapsed(time.monotonic() - self._start)
        filled = min(int(_BAR_WIDTH * done_count / total), _BAR_WIDTH) if total else 0
        bar = (
            f"[{Theme.PRIMARY}]{'█' * filled}[/{Theme.PRIMARY}]"
            f"[{Theme.MUTED}]{'░' * (_BAR_WIDTH - filled)}[/{Theme.MUTED}]"
        )
        return f"{GUTTER}{bar}  [{Theme.MUTED}]{done_count}/{total} · {elapsed}[/{Theme.MUTED}]"

    def _failed_item_lines(self, phase: ProgressPhase) -> list[str]:
        """Render the failed items of *phase* with their short reason."""
        lines: list[str] = []
        for item in phase.items:
            if item.state != State.FAILED:
                continue
            lines.append(self._item_line(item))
            if item.detail:
                lines.append(
                    f"    [{Theme.MUTED}]{escape(item.detail)}[/{Theme.MUTED}]"
                )
        return lines

    # -- Live block ----------------------------------------------------------

    def render_live(self) -> str:
        """Build the live block as a Rich markup string.

        Every phase is visible from the start.  Nested items are shown only
        under the currently active phase; resolved phases collapse to their
        summary line, except a failing phase which keeps its failed items.
        """
        lines: list[str] = [self._header_text(), self._rule()]

        for phase in self.phases:
            lines.append(self._phase_line(phase))
            if phase.state == State.ACTIVE and phase.items:
                visible, hidden = self.visible_items(phase)
                lines.extend(self._item_line(item) for item in visible)
                if hidden:
                    pending = state_symbol(State.PENDING)
                    lines.append(
                        f"{GUTTER}  [{Theme.MUTED}]{pending} +{hidden} more[/{Theme.MUTED}]"
                    )
            elif phase.state in (State.FAILED, State.PARTIAL):
                lines.extend(self._failed_item_lines(phase))

        lines.append(self._rule())
        lines.append(self._progress_bar())
        return "\n".join(lines)

    def live_group(self) -> Group:
        """Return the live block as a Rich renderable."""
        return Group(
            *(Text.from_markup(line) for line in self.render_live().split("\n"))
        )

    # -- Final output --------------------------------------------------------

    def _summary_line(self) -> str:
        """Build the closing line: ``✓ ready in 8.3s`` or the partial form."""
        total_elapsed = format_elapsed(time.monotonic() - self._start)
        if self.succeeded:
            symbol = state_symbol(State.DONE)
            return (
                f"{GUTTER}[{Theme.SUCCESS}]{symbol} ready[/{Theme.SUCCESS}] "
                f"[{Theme.MUTED}]in {total_elapsed}[/{Theme.MUTED}]"
            )

        done_items = sum(
            1 for p in self.phases for i in p.items if i.state == State.DONE
        )
        failed_items = sum(
            1 for p in self.phases for i in p.items if i.state == State.FAILED
        )
        total_items = self.total or (done_items + failed_items)
        symbol = state_symbol(State.PARTIAL)
        style = Theme.ERROR if done_items == 0 and failed_items else Theme.WARNING
        return (
            f"{GUTTER}[{style}]{symbol} {done_items} of {total_items} {self.unit}[/{style}] "
            f"[{Theme.MUTED}]in {total_elapsed}[/{Theme.MUTED}]"
        )

    @property
    def succeeded(self) -> bool:
        """True when every phase resolved to DONE."""
        return bool(self.phases) and all(p.state == State.DONE for p in self.phases)

    def render_summary(self) -> str:
        """Build the collapsed result block.

        Nested detail drops on full success but the per-phase timings stay —
        they are the useful part.  A failing phase keeps its failed items.
        """
        lines: list[str] = [self._header_text(), self._rule()]
        for phase in self.phases:
            lines.append(self._phase_line(phase))
            if phase.state in (State.FAILED, State.PARTIAL):
                lines.extend(self._failed_item_lines(phase))
        lines.append(self._rule())
        lines.append(self._summary_line())
        return "\n".join(lines)

    def render_failure(self, fix_hints: Optional[list[str]] = None) -> str:
        """Build the result block plus copy-pasteable fix commands.

        Args:
            fix_hints: Fix commands, one per line, in the order to run them.
        """
        lines = [self.render_summary()]
        arrow = sym("ARROW")
        for hint in fix_hints or []:
            lines.append(
                f"{GUTTER}[{Theme.MUTED}]{arrow} {escape(hint)}[/{Theme.MUTED}]"
            )
        return "\n".join(lines)

    # -- Plain / CI path -----------------------------------------------------

    def _plain_phase_line(self, phase: ProgressPhase) -> str:
        """Render one plain-text line for a resolved phase."""
        name = phase.name.ljust(_PHASE_NAME_WIDTH)
        parts = [f"{GUTTER}{state_symbol(phase.state)} {name}"]
        details = []
        if phase.summary:
            details.append(phase.summary)
        if phase.elapsed_s:
            details.append(format_elapsed(phase.elapsed_s))
        if details:
            parts.append(f" {' · '.join(details)}")
        return "".join(parts).rstrip()

    def _emit_plain_transitions(self) -> None:
        """Print a line for each phase that resolved since the last call."""
        for phase in self.phases:
            if phase.state not in _RESOLVED_STATES or id(phase) in self._plain_emitted:
                continue
            self._plain_emitted.add(id(phase))
            console.print(self._plain_phase_line(phase), markup=False, highlight=False)
            for item in phase.items:
                if item.state != State.FAILED:
                    continue
                console.print(
                    f"{GUTTER}  {state_symbol(State.FAILED)} {item.name}",
                    markup=False,
                    highlight=False,
                )
                if item.detail:
                    console.print(
                        f"{GUTTER}    {item.detail}", markup=False, highlight=False
                    )

    def render_plain(self) -> str:
        """Build the whole operation as plain text (no markup, no cursor codes).

        Used by the non-interactive path and by callers that want the full
        block as a single string.
        """
        lines: list[str] = [self._plain_header()]
        for phase in self.phases:
            lines.append(self._plain_phase_line(phase))
            for item in phase.items:
                if item.state != State.FAILED:
                    continue
                lines.append(f"{GUTTER}  {state_symbol(State.FAILED)} {item.name}")
                if item.detail:
                    lines.append(f"{GUTTER}    {item.detail}")

        total_elapsed = format_elapsed(time.monotonic() - self._start)
        if self.succeeded:
            lines.append(f"{GUTTER}{state_symbol(State.DONE)} ready in {total_elapsed}")
        else:
            done_items = sum(
                1 for p in self.phases for i in p.items if i.state == State.DONE
            )
            failed_items = sum(
                1 for p in self.phases for i in p.items if i.state == State.FAILED
            )
            total_items = self.total or (done_items + failed_items)
            lines.append(
                f"{GUTTER}{state_symbol(State.PARTIAL)} {done_items} of {total_items} "
                f"{self.unit} in {total_elapsed}"
            )
        return "\n".join(lines)

    # -- High-level orchestration -------------------------------------------

    def print_result(self, fix_hints: Optional[list[str]] = None) -> None:
        """Print the final result, selecting interactive vs. plain output.

        In plain mode the per-phase lines were already emitted as they
        resolved, so only the closing summary and fix hints are printed.

        Args:
            fix_hints: Fix commands shown when the operation did not fully
                succeed.
        """
        self.stop()
        if is_interactive():
            console.print(
                self.render_summary()
                if self.succeeded
                else self.render_failure(fix_hints)
            )
            return

        arrow = sym("ARROW")
        if self.succeeded:
            console.print(
                f"{GUTTER}{state_symbol(State.DONE)} ready in "
                f"{format_elapsed(time.monotonic() - self._start)}",
                markup=False,
                highlight=False,
            )
        else:
            done_items = sum(
                1 for p in self.phases for i in p.items if i.state == State.DONE
            )
            failed_items = sum(
                1 for p in self.phases for i in p.items if i.state == State.FAILED
            )
            total_items = self.total or (done_items + failed_items)
            console.print(
                f"{GUTTER}{state_symbol(State.PARTIAL)} {done_items} of {total_items} "
                f"{self.unit} in {format_elapsed(time.monotonic() - self._start)}",
                markup=False,
                highlight=False,
            )
            for hint in fix_hints or []:
                console.print(f"{GUTTER}{arrow} {hint}", markup=False, highlight=False)


def create_install_renderer(
    packages: Sequence[str],
    strategy: str = "pip",
    total: int = 0,
) -> tuple[ProgressRenderer, ProgressPhase, ProgressPhase, ProgressPhase]:
    """Create a renderer pre-configured with the three install phases.

    Args:
        packages: Package specs being installed, one nested item each.
        strategy: ``"uv"`` or ``"pip"``.
        total: Total package count for the bar (defaults to ``len(packages)``).

    Returns:
        ``(renderer, resolve_phase, download_phase, install_phase)``.
    """
    resolve = ProgressPhase(name="resolve")
    download = ProgressPhase(name="download")
    install = ProgressPhase(
        name="install",
        items=[ProgressItem(name=pkg) for pkg in packages],
    )
    renderer = ProgressRenderer(
        title="installing",
        strategy=strategy,
        total=total or len(packages),
        phases=[resolve, download, install],
    )
    return renderer, resolve, download, install
