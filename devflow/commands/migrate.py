"""Migrate command group — Alembic integration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from devflow.console import console

app = typer.Typer(help="Alembic database migration commands.")


def _find_alembic_ini() -> Path:
    """Search for alembic.ini from cwd upward."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / "alembic.ini"
        if candidate.exists():
            return candidate
    return Path.cwd() / "alembic.ini"


def _run_alembic(args: list[str], cwd: Path) -> None:
    """Run an alembic sub-command and stream output to the terminal."""
    cmd = [sys.executable, "-m", "alembic"] + args
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=False)
    if result.returncode != 0:
        console.print(
            Panel(
                f"[red]✗[/red]  Alembic exited with code {result.returncode}.",
                title="[bold red]Migration Error[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(result.returncode)


@app.command("init")
def migrate_init() -> None:
    """Initialize Alembic in the current project directory.

    Runs: alembic init alembic
    """
    cwd = Path.cwd()
    console.print(
        Panel(
            f"Initializing Alembic in [cyan]{cwd}[/cyan]",
            title="[bold]DevFlow[/bold] — Migrate Init",
            border_style="cyan",
        )
    )
    _run_alembic(["init", "alembic"], cwd)
    console.print(
        "[bold green]✓[/bold green]  Alembic initialized.\n"
        "[dim]Edit [cyan]alembic/env.py[/cyan] to point to your database URL and import your models.[/dim]"
    )


@app.command("make")
def migrate_make(
    message: Annotated[str, typer.Argument(help='Migration message, e.g. "add user table"')],
) -> None:
    """Generate a new Alembic migration.

    Runs: alembic revision --autogenerate -m MESSAGE
    """
    ini_path = _find_alembic_ini()
    cwd = ini_path.parent
    console.print(
        Panel(
            f"Generating migration: [bold cyan]{message}[/bold cyan]",
            title="[bold]DevFlow[/bold] — Migrate Make",
            border_style="cyan",
        )
    )
    _run_alembic(["revision", "--autogenerate", "-m", message], cwd)
    console.print("[bold green]✓[/bold green]  Migration file created.")


@app.command("run")
def migrate_run() -> None:
    """Apply all pending Alembic migrations.

    Runs: alembic upgrade head
    """
    ini_path = _find_alembic_ini()
    cwd = ini_path.parent
    console.print(
        Panel(
            "Applying all pending migrations (upgrade head)...",
            title="[bold]DevFlow[/bold] — Migrate Run",
            border_style="cyan",
        )
    )
    _run_alembic(["upgrade", "head"], cwd)
    console.print("[bold green]✓[/bold green]  All migrations applied.")


@app.command("rollback")
def migrate_rollback() -> None:
    """Revert the last applied Alembic migration.

    Runs: alembic downgrade -1
    """
    ini_path = _find_alembic_ini()
    cwd = ini_path.parent
    console.print(
        Panel(
            "Rolling back the last migration (downgrade -1)...",
            title="[bold]DevFlow[/bold] — Migrate Rollback",
            border_style="yellow",
        )
    )
    _run_alembic(["downgrade", "-1"], cwd)
    console.print("[bold green]✓[/bold green]  Last migration reverted.")
