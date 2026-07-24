"""Shared UX utilities for Kaira CLI — used by all Phase 4 command modules."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from kaira.console import console

# ---------------------------------------------------------------------------
# Fuzzy suggestion helper
# ---------------------------------------------------------------------------

try:
    from rapidfuzz import process as _rf_process  # type: ignore[import]

    _HAS_RAPIDFUZZ = True
except ImportError:
    import difflib as _difflib  # type: ignore[assignment]

    _HAS_RAPIDFUZZ = False


def suggest_did_you_mean(query: str, candidates: list[str], limit: int = 3) -> list[str]:
    """Return closest matches for *query* from *candidates*.

    Uses rapidfuzz when available, falls back to difflib.

    Args:
        query: The string the user typed.
        candidates: Valid options to compare against.
        limit: Maximum number of suggestions to return.

    Returns:
        List of close matches, may be empty.
    """
    if not candidates:
        return []
    if _HAS_RAPIDFUZZ:
        results = _rf_process.extract(query, candidates, limit=limit)
        return [r[0] for r in results if r[1] >= 50]
    else:
        return _difflib.get_close_matches(query, candidates, n=limit, cutoff=0.5)


# ---------------------------------------------------------------------------
# Next-steps block
# ---------------------------------------------------------------------------


def print_next_steps(steps: list[str], quiet: bool = False) -> None:
    """Print a Rich 'Next Steps' panel with up to 4 suggestions.

    Args:
        steps: List of next-step suggestion strings (Rich markup OK).
        quiet: If True, suppress output entirely.
    """
    if quiet or not steps:
        return
    capped = steps[:4]
    lines = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(capped))
    console.print(
        Panel(
            lines,
            title="[bold cyan]Next Steps[/bold cyan]",
            border_style="cyan",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# Typed confirmation for destructive commands
# ---------------------------------------------------------------------------


def typed_confirmation(resource_name: str, action: str, force: bool = False) -> bool:
    """Require the user to type a resource name to confirm a destructive action.

    Args:
        resource_name: The name the user must type to confirm (e.g. database name).
        action: Human-readable description of what will happen.
        force: If True and APP_ENV != production, bypass the prompt.

    Returns:
        True if confirmed, False if aborted.

    Raises:
        typer.Exit: Always when APP_ENV=production (blocked in production).
    """
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env == "production":
        console.print(
            Panel(
                "[red]❌ Blocked: destructive commands are never permitted in production.\n"
                "Set APP_ENV to a non-production value to proceed.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if force:
        return True

    console.print(
        f"[yellow]⚠️  {action}[/yellow]\n"
        f"  Type [bold]{resource_name}[/bold] to confirm, or press Enter to abort:"
    )
    answer = typer.prompt("", default="")
    if answer.strip() != resource_name:
        console.print("[dim]Aborted.[/dim]")
        return False
    return True


# ---------------------------------------------------------------------------
# Credential masking
# ---------------------------------------------------------------------------

_CREDENTIAL_RE = re.compile(
    r"((?:postgresql|mysql|mongodb|redis|amqp|postgresql\+asyncpg|mysql\+aiomysql)"
    r"(?:\+\w+)?://)"
    r"([^:@/]+):([^@/]+)@",
    re.IGNORECASE,
)


def mask_credentials(url: str) -> str:
    """Mask username and password in a database/broker connection URL.

    Args:
        url: Raw connection URL string.

    Returns:
        URL with credentials replaced by '***'.
    """
    return _CREDENTIAL_RE.sub(r"\1***:***@", url)


# ---------------------------------------------------------------------------
# Sensitive key redaction (for history file)
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS = re.compile(
    r"(secret|token|password|passwd|key|dsn|api.key)",
    re.IGNORECASE,
)


def redact_sensitive(key: str, value: str) -> str:
    """Return '[REDACTED]' if key matches a sensitive pattern, else the original value.

    Args:
        key: The argument key name.
        value: The argument value string.

    Returns:
        '[REDACTED]' if key is sensitive, else value unchanged.
    """
    if _SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    return value


# ---------------------------------------------------------------------------
# Require-project guard
# ---------------------------------------------------------------------------


def require_project() -> Path:
    """Assert that a .kaira.json exists in the CWD tree.

    Returns:
        Path to the config file.

    Raises:
        typer.Exit: With code 1 if no config is found.
    """
    from kaira.config import find_config_path

    config_path = find_config_path()
    if not config_path.exists():
        console.print(
            Panel(
                "[red]No .kaira.json found in the current directory or any parent.\n\n"
                "Start a new project with:[/red]\n"
                "  [bold cyan]kaira init <name>[/bold cyan]",
                title="[red]Not in a Kaira project[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)
    return config_path


# ---------------------------------------------------------------------------
# History file helper
# ---------------------------------------------------------------------------

_HISTORY_DIR = ".kaira"
_HISTORY_FILE = "history.jsonl"


def append_history(command: str, args: dict[str, str]) -> None:
    """Append a command invocation record to .kaira/history.jsonl.

    Sensitive argument values are automatically redacted before writing.
    The history dir is gitignored by the generated project templates.

    Args:
        command: The kaira command string (e.g. 'generate model').
        args: Dict of argument keys → values.
    """
    import datetime

    history_dir = Path.cwd() / _HISTORY_DIR
    try:
        history_dir.mkdir(exist_ok=True)
        history_path = history_dir / _HISTORY_FILE
        record = {
            "command": command,
            "args": {k: redact_sensitive(k, str(v)) for k, v in args.items()},
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # Never crash the CLI because history writing failed
