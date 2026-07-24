"""Kaira run command -- start the FastAPI dev/prod server.

Wraps the official ``fastapi dev`` / ``fastapi run`` CLI (from fastapi[standard])
with a smart fallback to plain uvicorn when the fastapi CLI is not available.

Usage examples
--------------
  kaira run                        # auto-detect entry, dev mode
  kaira run --entry app/main.py    # explicit entry file
  kaira run --port 9000            # custom port
  kaira run --host 0.0.0.0         # bind all interfaces
  kaira run --prod                 # production mode (fastapi run / no reload)
  kaira run --no-reload            # disable hot-reload in dev mode
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

from kaira.console import console

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


def _db_banner_info(cwd: Path) -> Optional[tuple[str, str, str, bool]]:
    """Return ``(engine, name, mode, online)`` for the run banner, or ``None``.

    Reads the resolved values from ``.kaira.json`` (``db_type``/``db_name``/
    ``db_mode``) so the banner reports the same database the app binds — without
    connecting. Returns ``None`` when not inside a Kaira project.
    """
    config_path = cwd / ".kaira.json"
    if not config_path.exists():
        return None
    try:
        import json

        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    engine = data.get("db_type", "sqlite")
    name = data.get("db_name") or "—"
    mode = data.get("db_mode", "online")
    online = mode != "offline"
    return engine, name, mode, online


def _module_importable(name: str, python_exe: Optional[str] = None) -> bool:
    """Return True if *name* can be imported (installed as a module)."""
    if python_exe and python_exe != sys.executable:
        try:
            res = subprocess.run(
                [python_exe, "-c", f"import {name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return res.returncode == 0
        except Exception:
            return False
    else:
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
    sql: Annotated[
        bool,
        typer.Option("--sql", "--verbose", help="Show SQL echo for this run (KAIRA_SQL_ECHO=1)."),
    ] = False,
) -> None:
    """Start the FastAPI server using 'fastapi dev' or 'fastapi run'.

    Falls back to 'uvicorn' when the 'fastapi' CLI (fastapi[standard]) is
    not installed.

    Examples
    --------
    kaira run
    kaira run --prod
    kaira run --port 9000 --host 0.0.0.0
    kaira run --entry app/main.py
    kaira run --no-reload
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
                    "Specify one with:  [bold cyan]kaira run --entry PATH[/bold cyan]",
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
    from kaira.config import get_venv_python

    python_exe = get_venv_python(cwd)

    # Prefer the official FastAPI CLI (ships with fastapi[standard]); fall back to
    # plain uvicorn only when it is unavailable.
    fastapi_cli = (
        shutil.which("fastapi") is not None
        or _module_importable("fastapi_cli", python_exe)
    )
    uvicorn_available = (
        shutil.which("uvicorn") is not None
        or _module_importable("uvicorn", python_exe)
    )

    if not fastapi_cli and not uvicorn_available:
        console.print(
            Panel(
                "[red]Neither the [bold]fastapi[/bold] CLI ([bold]fastapi[standard][/bold]) "
                "nor [bold]uvicorn[/bold] is installed.\n\n"
                '[dim]Install with:[/dim]  '
                '[bold]pip install "fastapi[standard]"[/bold]',
                title="[red]x  No server runner found[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    module = _module_from_path(entry_path, cwd)

    if fastapi_cli:
        # `fastapi dev` reloads by default; `fastapi run` is the no-reload/prod path.
        subcmd = "dev" if (not prod and reload) else "run"
        cmd = [
            python_exe, "-m", "fastapi", subcmd,
            entry_display,
            "--host", host,
            "--port", str(port),
        ]
        runner_name = f"fastapi {subcmd}"
        runner_note = "Using the official FastAPI CLI (fastapi[standard])"
    else:
        cmd = [
            python_exe, "-m", "uvicorn",
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
        runner_note = "fastapi CLI not found — falling back to uvicorn"

    # ── Launch banner ─────────────────────────────────────────────────────────
    info_table = Table(box=rich_box.SIMPLE, show_header=False, padding=(0, 1))
    info_table.add_column("", style="dim", width=14)
    info_table.add_column("", style="bold")

    info_table.add_row("Mode",       f"[{mode_color}]{mode}[/{mode_color}]")
    info_table.add_row("Entry",      f"[white]{entry_display}[/white]")
    info_table.add_row("Runner",     f"[white]{runner_name}[/white]")
    # Database + online/offline mode — the primary place a developer learns which
    # DB they're on (Phase 6, Features 2.3 & 4). Reads the resolved values only.
    db_info = _db_banner_info(cwd)
    if db_info:
        from kaira.core.theme import Theme, sym

        engine_name, db_name, db_mode, online = db_info
        badge_style = Theme.SUCCESS if online else Theme.WARNING
        badge_icon = sym("OK") if online else sym("WARN")
        info_table.add_row(
            "Database",
            f"[white]{engine_name}[/white]  [dim]·[/dim]  [white]{db_name}[/white]  "
            f"[dim]·[/dim]  [{badge_style}]{badge_icon} {db_mode}[/{badge_style}]",
        )
    if sql:
        info_table.add_row("SQL echo", "[yellow]on[/yellow]")
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
            title="[bold cyan]Kaira  --  Launching FastAPI Server[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    # Type-fidelity heads-up (§3.4): SQLite can't faithfully mirror Postgres
    # native types. Flag only — never blocks the run.
    if db_info and db_info[0] == "postgresql":
        try:
            import json

            from kaira.core.provisioner import models_with_native_types

            data = json.loads((cwd / ".kaira.json").read_text(encoding="utf-8"))
            flagged = models_with_native_types(data.get("generated_models", []))
            for model_name in flagged:
                console.print(
                    f"  [yellow]⚠️  model {model_name} uses a Postgres-native type — "
                    f"not faithfully represented in offline SQLite mode[/yellow]"
                )
        except (OSError, ValueError):
            pass

    console.print("  [dim]Press [bold]Ctrl+C[/bold] to stop the server.[/dim]\n")

    # ── Hand off to server process (replaces current process stdin/stdout) ────
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # SQL echo is off by default; `--sql`/`--verbose` opts in for this run only.
    if sql:
        env["KAIRA_SQL_ECHO"] = "1"

    try:
        subprocess.run(cmd, cwd=str(cwd), env=env)
    except KeyboardInterrupt:
        pass
    finally:
        console.print()
        console.print(
            Panel(
                "[bold]Server stopped.[/bold]  "
                "[dim]Run [cyan]kaira run[/cyan] to start again.[/dim]",
                border_style="bright_black",
                padding=(0, 2),
            )
        )
