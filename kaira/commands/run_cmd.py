"""Kaira run command -- start the Kaira Framework runtime server."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box as rich_box
from rich.panel import Panel
from rich.table import Table

from kaira.console import console
from kaira.core.ports import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PortResolution,
    PortUnavailableError,
    clear_server,
    record_server,
    resolve_port,
)

app = typer.Typer(help="Start the Kaira Framework runtime server.")


def _shift_note(resolution: PortResolution) -> str:
    """Describe a port shift in the launch banner."""
    return (
        f"[bold]{resolution.port}[/bold]  "
        f"[dim yellow]moved from {resolution.requested} — "
        f"another server is on it[/dim yellow]"
    )


def _db_banner_info(cwd: Path) -> tuple[str, str, str, bool] | None:
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


@app.callback(invoke_without_command=True)
def run_command(
    ctx: typer.Context,
    host: Annotated[
        str,
        typer.Option("--host", "-H", help="Host to bind the server to."),
    ] = DEFAULT_HOST,
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Preferred port. Moves to the next free one if it is taken.",
        ),
    ] = DEFAULT_PORT,
    strict_port: Annotated[
        bool,
        typer.Option(
            "--strict-port",
            help="Fail if the requested port is taken instead of moving to the next.",
        ),
    ] = False,
    reload: Annotated[
        bool,
        typer.Option(
            "--reload/--no-reload", help="Enable/disable hot-reload (dev mode only)."
        ),
    ] = True,
    prod: Annotated[
        bool,
        typer.Option(
            "--prod", help="Run in production mode (no reload)."
        ),
    ] = False,
    sql: Annotated[
        bool,
        typer.Option(
            "--sql", "--verbose", help="Show SQL echo for this run (KAIRA_SQL_ECHO=1)."
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            "-d",
            help="Verbose logs: per-layer traces, request ids, server lifecycle.",
        ),
    ] = False,
    access_log: Annotated[
        bool,
        typer.Option(
            "--access-log", help="Also print uvicorn's own access log line per request."
        ),
    ] = False,
) -> None:
    """Start the Kaira Framework runtime server via KairaApp."""
    if ctx.invoked_subcommand is not None:
        return

    cwd = Path.cwd()

    import os

    if sql:
        os.environ["KAIRA_SQL_ECHO"] = "1"
    if debug:
        os.environ["KAIRA_LOG_LEVEL"] = "DEBUG"
    if access_log:
        os.environ["KAIRA_ACCESS_LOG"] = "1"

    try:
        resolved = resolve_port(host=host, requested=port, strict=strict_port)
        active_port = resolved.port
        if resolved.shifted:
            console.print(
                f"[yellow]Port {port} in use; moved to {active_port}[/yellow]"
            )
    except PortUnavailableError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    # ── KairaApp Runtime ─────────────────────────────────────
    from kaira.app import KairaApp
    from kaira.config import get_config
    from kaira.core.theme import Theme, sym

    cfg = get_config()
    app_instance = KairaApp(
        project_name=cfg.db_name or cwd.name,
        tier=getattr(cfg, "tier", "standard"),
        providers=getattr(cfg, "providers", ["cache", "auth"]),
    )

    mode = "production" if prod else "development"
    mode_color = "yellow" if prod else "green"
    entry_display = "main:app" if (cwd / "main.py").exists() else "KairaApp"

    # ── Launch Dashboard Banner ──────────────────────────────
    info_table = Table(box=rich_box.SIMPLE, show_header=False, padding=(0, 1))
    info_table.add_column("", style="dim", width=14)
    info_table.add_column("", style="bold")

    info_table.add_row("Mode", f"[{mode_color}]{mode}[/{mode_color}]")
    info_table.add_row("Runtime", f"[{Theme.PRIMARY}]Khaira Framework Runtime (KairaApp)[/{Theme.PRIMARY}]")
    info_table.add_row("Entry", f"[white]{entry_display}[/white]")

    db_info = _db_banner_info(cwd)
    if db_info:
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
    info_table.add_row(
        "Logs",
        "[yellow]debug[/yellow]  [dim]per-layer traces, request ids[/dim]"
        if debug
        else "[white]info[/white]  [dim]one line per request — add --debug for detail[/dim]",
    )
    if resolved.shifted:
        info_table.add_row("Port", _shift_note(resolved))
    info_table.add_row("URL", f"[bold cyan]http://{host}:{active_port}[/bold cyan]")
    info_table.add_row("Docs", f"[dim]http://{host}:{active_port}/docs[/dim]")
    info_table.add_row("ReDoc", f"[dim]http://{host}:{active_port}/redoc[/dim]")
    if not prod:
        reload_label = "[green]on[/green]" if reload else "[dim]off[/dim]"
        info_table.add_row("Hot-reload", reload_label)

    console.print()
    console.print(
        Panel(
            info_table,
            title="[bold cyan]⚡ Khaira  —  Launching Framework Server[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print("  [dim]Press [bold]Ctrl+C[/bold] to stop the server.[/dim]\n")

    # ── Hand off to runtime process with lifecycle tracking ──
    record_server(host, active_port, cwd)
    try:
        app_instance.run(dev=not prod, host=host, port=active_port)
    except KeyboardInterrupt:
        pass
    finally:
        clear_server(cwd)

    console.print()
    console.print(
        Panel(
            "[bold]Server stopped.[/bold]  "
            "[dim]Run [cyan]khaira run[/cyan] to start again.[/dim]",
            border_style="bright_black",
            padding=(0, 2),
        )
    )
    return
