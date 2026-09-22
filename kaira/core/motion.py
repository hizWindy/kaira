"""Kaira motion layer — timed reveals for the terminal surfaces.

Animation in a CLI is a liability unless three things hold, so all three are
enforced here rather than left to each call site:

* **It is bounded.**  One budget (:data:`MOTION_BUDGET_S`) covers the whole
  invocation, and every effect draws from that single pool rather than each
  honouring its own ceiling.  Within an effect the per-frame delay is the
  granted budget *divided* by the frame count, so a longer dashboard animates
  faster rather than taking longer, and when the share left cannot buy a step
  worth seeing the effect is dropped instead of overrunning.  The wall clock of
  ``kaira`` does not grow with the size of its output.
* **It is additive.**  A reveal prints the same lines in the same order as the
  still version — it only spaces them out in time.  Piping, redirecting, or
  reading the output back gives byte-identical text, because the animation adds
  no characters, only pauses.
* **It gets out of the way.**  Not a TTY, ``NO_COLOR``, ``CI``, ``--quiet``, or
  ``KAIRA_NO_MOTION`` and the effect degrades to plain printing.  Ctrl-C during
  an effect flushes the remaining frames immediately instead of leaving a
  half-painted surface on screen.

Two primitives, deliberately: :func:`reveal` for a block that cascades into
place, and :func:`play` for a single line that changes in place.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from typing import Any

from rich.console import RenderableType
from rich.live import Live
from rich.text import Text

from kaira.console import console
from kaira.core.theme import banner_is_terminal, is_interactive, is_quiet

MOTION_BUDGET_S = 0.34
"""Total wall time *one invocation* may spend on motion, across every effect.

Chosen to sit under the ~400 ms mark where a terminal stops feeling immediate.
The ceiling is per invocation rather than per effect because what a developer
waits for is the surface, not its parts: two effects each honouring a 340 ms
budget still leaves them looking at 680 ms of animation.
"""

PLAY_BUDGET_S = 0.12
"""Default share for a :func:`play` effect — an accent, not the main event."""

REVEAL_BUDGET_S = 0.22
"""Default share for a :func:`reveal` cascade — the surface itself."""

MIN_STEP_S = 0.006
"""Floor on a single step.

Below this a stagger does not read as motion, so rather than spend the budget
on a flicker the effect is dropped and the lines print at once.
"""

MAX_STEP_S = 0.040
"""Ceiling on a single step, so a two-line reveal does not crawl."""

DISABLE_ENV_VARS = ("KAIRA_NO_MOTION", "NO_MOTION")
"""Opt-outs honoured regardless of terminal capability."""

CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "TF_BUILD")
"""CI markers.  A build log is read after the fact, where timing is only cost."""


# ---------------------------------------------------------------------------
# The budget pool
#
# One pool per invocation, drawn from by every effect in the order they run.
# Without it each effect would honour its own ceiling and the surface would
# still take their sum — which is the only number the developer experiences.
# ---------------------------------------------------------------------------

_spent = 0.0


def reset_budget() -> None:
    """Return the motion budget to full for a new invocation.

    A CLI process runs one invocation, so the pool would never need resetting
    in production — but a test suite, or anything embedding the CLI, runs many
    through one process, and a pool that only ever drains would silently stop
    animating after the first.
    """
    global _spent
    _spent = 0.0


def budget_remaining() -> float:
    """Return how much of this invocation's motion budget is left."""
    return max(0.0, MOTION_BUDGET_S - _spent)


def _claim(requested: float) -> float:
    """Reserve up to *requested* seconds from this invocation's budget."""
    global _spent
    granted = min(requested, budget_remaining())
    _spent += granted
    return granted


def motion_enabled() -> bool:
    """Return True when this invocation may animate.

    Every condition is a reason the pauses would be waste or damage: a log file
    records no motion but pays for it, a CI runner is nobody's live terminal,
    ``--quiet`` asked for less, and ``NO_COLOR`` (via :func:`is_interactive`)
    is the standing signal for plain output.
    """
    if any(os.environ.get(name) for name in DISABLE_ENV_VARS):
        return False
    if any(os.environ.get(name) for name in CI_ENV_VARS):
        return False
    if is_quiet():
        return False
    return is_interactive() and banner_is_terminal()


def _step_delay(frames: int, budget: float) -> float:
    """Return the per-frame pause that fits *frames* inside *budget*.

    Returns ``0.0`` — print everything at once — when the budget cannot buy a
    step long enough to read as motion.  The alternative, honouring the floor
    and overrunning, is how a long surface ends up costing a second to draw for
    an effect nobody can see anyway.
    """
    if frames <= 1 or budget <= 0:
        return 0.0
    delay = budget / frames
    if delay < MIN_STEP_S:
        return 0.0
    # Only ever lowered from here, so the whole effect still fits the budget.
    return min(delay, MAX_STEP_S)


def _is_blank(line: RenderableType) -> bool:
    """Return True for a line with nothing on it.

    Blank lines are spacing, not content: pausing after one spends budget on a
    beat the eye cannot see, and makes the lines that do carry text arrive late.
    """
    if isinstance(line, str):
        return not line.strip()
    if isinstance(line, Text):
        return not line.plain.strip()
    return False


def reveal(
    lines: Sequence[RenderableType],
    *,
    budget: float = REVEAL_BUDGET_S,
    printer: Callable[[RenderableType], Any] | None = None,
) -> None:
    """Print *lines* top to bottom, cascading when motion is enabled.

    Args:
        lines: Renderables in final order — markup strings or Rich objects.
        budget: Wall time to ask this invocation's pool for.  Granted in full
            only if earlier effects have left that much.
        printer: Sink for each line; defaults to the shared console.  Injectable
            so a surface can reveal onto stderr, or into a recorder, without the
            motion layer having to know which console it is driving.
    """
    emit = printer or console.print

    if not motion_enabled():
        for line in lines:
            emit(line)
        return

    delay = _step_delay(sum(1 for line in lines if not _is_blank(line)), _claim(budget))
    for index, line in enumerate(lines):
        try:
            emit(line)
            if delay and not _is_blank(line):
                time.sleep(delay)
        except KeyboardInterrupt:
            # The user asked for the rest now, not for a truncated surface.
            for remaining in lines[index + 1 :]:
                emit(remaining)
            return


def play(
    frames: Sequence[RenderableType],
    final: RenderableType,
    *,
    budget: float = PLAY_BUDGET_S,
) -> None:
    """Repaint one line through *frames*, leaving *final* on screen.

    The last thing printed is always *final*, whether the frames played, were
    skipped, or were interrupted — so what stays in the scrollback is the still
    version of the surface and never an intermediate frame.

    Args:
        frames: Intermediate states, in order.
        final: The state that must remain once the effect ends.
        budget: Wall time to ask this invocation's pool for.  Granted in full
            only if earlier effects have left that much.
    """
    if not motion_enabled() or not frames:
        console.print(final)
        return

    delay = _step_delay(len(frames) + 1, _claim(budget))
    if not delay:
        console.print(final)
        return

    try:
        with Live(
            frames[0],
            console=console,
            refresh_per_second=max(int(1 / delay), 1),
            transient=False,
        ) as live:
            for frame in list(frames[1:]) + [final]:
                time.sleep(delay)
                live.update(frame)
    except KeyboardInterrupt:
        console.print(final)
