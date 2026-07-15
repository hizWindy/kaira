"""First-run onboarding for DevFlow.

Shown once per machine when no ``~/.devflow/config.json`` exists and stdin is
a TTY.  Writes ``experience_level``, ``telemetry``, and ``theme`` preferences.
Telemetry is strictly opt-in; records command names + durations only — never
paths, arguments, or project names.

Skip conditions (onboarding is NOT shown):
- stdin is not a TTY (CI / piped input)
- Any CLI flags or arguments are present in sys.argv (user knows what they want)
- ``~/.devflow/config.json`` already exists

``devflow config reset-onboarding`` re-triggers it by deleting the file.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import typer

from devflow.console import console
from devflow.core.theme import Theme, is_interactive, sym

_CONFIG_DIR = Path.home() / ".devflow"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def config_exists() -> bool:
    """Return True if the global DevFlow user config file exists."""
    return _CONFIG_FILE.exists()


def load_config() -> dict[str, Any]:
    """Load and return the global DevFlow user config dict.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict[str, Any]) -> None:
    """Persist *data* to ``~/.devflow/config.json`` with safe permissions.

    Creates ``~/.devflow/`` if it does not exist.  File is written with
    ``0600`` permissions so only the current user can read it.

    Args:
        data: Config dictionary to serialise and save.
    """
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows may not support chmod — silently ignore


def reset_config() -> None:
    """Delete the global DevFlow user config so onboarding runs again."""
    try:
        _CONFIG_FILE.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Onboarding guard
# ---------------------------------------------------------------------------


def _should_show(argv: list[str]) -> bool:
    """Determine whether onboarding should run given current conditions.

    Args:
        argv: sys.argv (excluding the program name).

    Returns:
        True only when ALL conditions are met:
        - stdin is a real TTY
        - ``NO_COLOR`` env var is not set
        - config file does not exist yet
        - No flags or arguments beyond the base ``devflow`` invocation
    """
    if not is_interactive():
        return False
    if config_exists():
        return False
    # Any sub-command or flag means the user knows the CLI already
    if len(argv) > 1:
        return False
    return True


# ---------------------------------------------------------------------------
# Onboarding flow
# ---------------------------------------------------------------------------


def run_onboarding() -> None:
    """Run the first-time interactive onboarding wizard.

    Collects experience level and telemetry preference, then writes
    ``~/.devflow/config.json``.  Safe to call unconditionally — it checks
    :func:`_should_show` internally and exits immediately if conditions are
    not met.
    """
    if not _should_show(sys.argv):
        return

    try:
        from devflow.core import prompts
    except ImportError:
        # InquirerPy not installed — skip onboarding silently
        return

    bolt = sym("BOLT")
    console.print(f"\n[{Theme.PRIMARY}]{bolt} Welcome to DevFlow![/{Theme.PRIMARY}]\n")
    console.print(
        f"[{Theme.MUTED}]This one-time setup takes 30 seconds and can always be reset with:[/{Theme.MUTED}]"
        f"\n  [{Theme.PRIMARY}]devflow config reset-onboarding[/{Theme.PRIMARY}]\n"
    )

    try:
        experience = prompts.select(
            "What describes you best?",
            choices=[
                ("new", "New to FastAPI  → suggests devflow guide + tutorial tips"),
                ("experienced", "Experienced dev  → minimal hints, straight to work"),
            ],
            default="experienced",
            flag="--experience",
        )

        telemetry = prompts.confirm(
            "Enable anonymous usage stats to improve DevFlow?\n"
            "  (no code, no secrets, no paths — command names + durations only)",
            default=False,
            flag="--telemetry/--no-telemetry",
        )
    except (typer.Exit, SystemExit):
        # User cancelled — save minimal defaults and continue
        experience = "experienced"
        telemetry = False

    cfg = {
        "experience_level": experience,
        "telemetry": telemetry,
        "theme": "default",
    }
    save_config(cfg)

    ok = sym("OK")
    console.print(f"\n[{Theme.SUCCESS}]{ok} Onboarding complete![/{Theme.SUCCESS}]")
    if experience == "new":
        console.print(
            f"  [{Theme.MUTED}]Tip: run[/{Theme.MUTED}] [{Theme.PRIMARY}]devflow guide[/{Theme.PRIMARY}]"
            f" [{Theme.MUTED}]to explore all topics.[/{Theme.MUTED}]"
        )
    console.print()
