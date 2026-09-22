"""Kaira run command -- start the Kaira Framework runtime server."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from kaira.console import console
from kaira.core.ports import DEFAULT_HOST, DEFAULT_PORT, PortUnavailableError, resolve_port

app = typer.Typer(help="Start the Kaira Framework runtime server.")


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
    from kaira.core.theme import Theme

    cfg = get_config()
    app_instance = KairaApp(
        project_name=cfg.db_name or cwd.name,
        tier=getattr(cfg, "tier", "standard"),
        providers=getattr(cfg, "providers", ["cache", "auth"]),
    )

    console.print(
        f"[{Theme.PRIMARY}]Starting Khaira Framework runtime on {host}:{active_port}...[/{Theme.PRIMARY}]"
    )
    app_instance.run(dev=not prod, host=host, port=active_port)
    return

