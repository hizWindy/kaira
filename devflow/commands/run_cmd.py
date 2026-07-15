"""DevFlow run command -- start the FastAPI dev/prod server.

Wraps the official ``fastapi dev`` / ``fastapi run`` CLI (from fastapi[standard])
with a smart fallback to plain uvicorn when the fastapi CLI is not available.

Usage examples
--------------
  devflow run                        # auto-detect entry, dev mode
  devflow run --entry app/main.py    # explicit entry file
  devflow run --port 9000            # custom port
  devflow run --host 0.0.0.0         # bind all interfaces
  devflow run --prod                 # production mode (fastapi run / no reload)
  devflow run --no-reload            # disable hot-reload in dev mode
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table
from rich import box as rich_box

from devflow.console import console

# ---------------------------------------------------------------------------
# Candidate entry-file search order
# ---------------------------------------------------------------------------

_ENTRY_CANDIDATES: list[str] = [
    "main.py",
    "app/main.py",
    "src/main.py",
    "app.py",
]


def _find_entry(cwd: Path) -> Optional[Path]:
    """Return the first existing candidate entry file, or None."""
    for candidate in _ENTRY_CANDIDATES:
        p = cwd / candidate
        if p.exists():
            return p
    return None


def _module_from_path(entry: Path, cwd: Path) -> str:
    """Convert a file path to a dotted Python module string for uvicorn.

    e.g. ``app/main.py`` -> ``app.main``
    """
    try:
        rel = entry.relative_to(cwd)
    except ValueError:
        rel = entry
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _module_importable(name: str) -> bool:
    """Return True if *name* can be imported (installed as a module)."""
    import importlib.util
    return importlib.util.find_spec(name) is not None


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

app = typer.Typer(help="Start the FastAPI development or production server.")


@app.callback(invoke_without_command=True)
def run_command(
    ctx: typer.Context,
    entry: Annotated[
        Optional[str],
        typer.Option("--entry", "-e", help="Entry file (e.g. main.py or app/main.py)."),
    ] = None,
    host: Annotated[
        str,
        typer.Option("--host", "-H", help="Host to bind the server to."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to bind the server to."),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option("--reload/--no-reload", help="Enable/disable hot-reload (dev mode only)."),
    ] = True,
    prod: Annotated[
        bool,
        typer.Option("--prod", help="Run in production mode (fastapi run / no reload)."),
    ] = False,
) -> None:
    """Start the FastAPI server using 'fastapi dev' or 'fastapi run'.

    Falls back to 'uvicorn' when the 'fastapi' CLI (fastapi[standard]) is
    not installed.

    Examples
    --------
    devflow run
    devflow run --prod
    devflow run --port 9000 --host 0.0.0.0
    devflow run --entry app/main.py
    devflow run --no-reload
    """
    if ctx.invoked_subcommand is not None:
        return

    cwd = Path.cwd()

    # ── Resolve entry file ────────────────────────────────────────────────────
    if entry:
        entry_path = Path(entry)
        if not entry_path.is_absolute():
            entry_path = cwd / entry_path
        if not entry_path.exists():
            console.print(
                Panel(
                    f"[red]Entry file not found:[/red] [bold]{entry}[/bold]\n\n"
                    "[dim]Check the path and try again, "
                    "or omit --entry to auto-detect.[/dim]",
                    title="[red]x  File not found[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)
    else:
        entry_path = _find_entry(cwd)
        if entry_path is None:
            candidates_str = "  |  ".join(_ENTRY_CANDIDATES)
            console.print(
                Panel(
                    "[yellow]Could not auto-detect an entry file.[/yellow]\n\n"
                    f"Searched for:  {candidates_str}\n\n"
                    "Specify one with:  [bold cyan]devflow run --entry PATH[/bold cyan]",
                    title="[yellow]!  Entry file not found[/yellow]",
                    border_style="yellow",
                )
            )
            raise typer.Exit(1)

    try:
        entry_display = str(entry_path.relative_to(cwd))
    except ValueError:
        entry_display = str(entry_path)

    mode = "production" if prod else "development"
    mode_color = "yellow" if prod else "cyan"

    import os

    # Fallback/Check: uvicorn
    if not shutil.which("uvicorn") and not _module_importable("uvicorn"):
        console.print(
            Panel(
                "[red]Neither [bold]fastapi[standard][/bold] nor "
                "[bold]uvicorn[/bold] is installed.\n\n"
                '[dim]Install with:[/dim]  '
                '[bold]pip install "fastapi[standard]"[/bold]',
                title="[red]x  No server runner found[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    module = _module_from_path(entry_path, cwd)
    cmd = [
        sys.executable, "-m", "uvicorn",
        f"{module}:app",
        "--host", host,
        "--port", str(port),
    ]
    if not prod and reload:
        cmd.extend([
            "--reload",
            "--reload-exclude", "*.db",
            "--reload-exclude", "*.db-journal",
            "--reload-exclude", "*.db-wal",
            "--reload-exclude", "*.log",
            "--reload-exclude", "__pycache__",
            "--reload-exclude", "*.pyc",
        ])

    runner_name = "uvicorn"
    runner_note = "Using uvicorn with database/log reload exclusions to prevent loops"

    # ── Launch banner ─────────────────────────────────────────────────────────
    info_table = Table(box=rich_box.SIMPLE, show_header=False, padding=(0, 1))
    info_table.add_column("", style="dim", width=14)
    info_table.add_column("", style="bold")

    info_table.add_row("Mode",       f"[{mode_color}]{mode}[/{mode_color}]")
    info_table.add_row("Entry",      f"[white]{entry_display}[/white]")
    info_table.add_row("Runner",     f"[white]{runner_name}[/white]")
    info_table.add_row("URL",        f"[bold cyan]http://{host}:{port}[/bold cyan]")
    info_table.add_row("Docs",       f"[dim]http://{host}:{port}/docs[/dim]")
    info_table.add_row("ReDoc",      f"[dim]http://{host}:{port}/redoc[/dim]")
    if not prod:
        reload_label = "[green]on[/green]" if reload else "[dim]off[/dim]"
        info_table.add_row("Hot-reload", reload_label)
    if runner_note:
        info_table.add_row("Note",   f"[dim yellow]{runner_note}[/dim yellow]")

    console.print()
    console.print(
        Panel(
            info_table,
            title="[bold cyan]DevFlow  --  Launching FastAPI Server[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print("  [dim]Press [bold]Ctrl+C[/bold] to stop the server.[/dim]\n")

    # ── Hand off to server process (replaces current process stdin/stdout) ────
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    try:
        subprocess.run(cmd, cwd=str(cwd), env=env)
    except KeyboardInterrupt:
        pass
    finally:
        console.print()
        console.print(
            Panel(
                "[bold]Server stopped.[/bold]  "
                "[dim]Run [cyan]devflow run[/cyan] to start again.[/dim]",
                border_style="bright_black",
                padding=(0, 2),
            )
        )
