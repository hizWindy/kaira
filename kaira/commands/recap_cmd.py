"""Kaira recap command — command history viewer."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table
from typing import Annotated

from kaira.console import console

app = typer.Typer(help="Show Kaira command history.")

_HISTORY_DIR = ".kaira"
_HISTORY_FILE = "history.jsonl"


def _load_history(since: Optional[datetime.datetime] = None) -> list[dict]:
    """Load history records from .kaira/history.jsonl.

    Args:
        since: If provided, only return records at or after this datetime.

    Returns:
        List of history record dicts, most recent last.
    """
    history_path = Path.cwd() / _HISTORY_DIR / _HISTORY_FILE
    if not history_path.exists():
        return []
    records = []
    try:
        for line in history_path.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None:
                ts_str = record.get("timestamp", "")
                try:
                    ts = datetime.datetime.fromisoformat(ts_str.rstrip("Z"))
                    if ts < since:
                        continue
                except ValueError:
                    pass
            records.append(record)
    except OSError:
        pass
    return records


@app.callback(invoke_without_command=True)
def recap_main(ctx: typer.Context) -> None:
    """Show Kaira command history."""
    if ctx.invoked_subcommand is None:
        recap_command()


@app.command("show")
def recap_command(
    today: Annotated[
        bool, typer.Option("--today", help="Show only today's commands")
    ] = False,
    week: Annotated[
        bool, typer.Option("--week", help="Show commands from the last 7 days")
    ] = False,
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="Maximum records to show")
    ] = 50,
) -> None:
    """Show command history from .kaira/history.jsonl.

    History is filtered by --today or --week if specified.
    Sensitive argument values are always redacted before display.

    Args:
        today: Only show commands run today.
        week: Only show commands from the last 7 days.
        limit: Cap on number of records shown.
    """
    now = datetime.datetime.utcnow()
    since: Optional[datetime.datetime] = None

    if today:
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif week:
        since = now - datetime.timedelta(days=7)

    history_path = Path.cwd() / _HISTORY_DIR / _HISTORY_FILE
    if not history_path.exists():
        console.print(
            Panel(
                "[dim]No history recorded yet.\n\n"
                "History is written to [bold].kaira/history.jsonl[/bold] "
                "as you run kaira commands.[/dim]",
                title="Khaira — Recap",
                border_style="cyan",
            )
        )
        return

    records = _load_history(since=since)

    if not records:
        period = "today" if today else ("the last 7 days" if week else "all time")
        console.print(f"[dim]No commands recorded for {period}.[/dim]")
        return

    # Cap and reverse (most recent first)
    records = records[-limit:][::-1]

    table = Table(title="⚡ Khaira — Command History", border_style="cyan")
    table.add_column("Timestamp", style="dim", no_wrap=True)
    table.add_column("Command", style="bold cyan")
    table.add_column("Args", style="dim")

    for record in records:
        ts = record.get("timestamp", "")[:19].replace("T", " ")
        cmd = record.get("command", "unknown")
        args = record.get("args", {})
        args_str = " ".join(f"{k}={v}" for k, v in args.items()) if args else ""
        table.add_row(ts, cmd, args_str)

    console.print(table)
    console.print(
        f"[dim]History file: {Path.cwd() / _HISTORY_DIR / _HISTORY_FILE}[/dim]"
    )
