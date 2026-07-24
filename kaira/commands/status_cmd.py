"""Kaira status command — live project snapshot."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

app = typer.Typer(help="Show live project status snapshot.")


def _ping_host(host: str, port: int, timeout: float = 1.0) -> bool:
    """Attempt a TCP connection to host:port within timeout seconds.

    Args:
        host: Hostname or IP to connect to.
        port: TCP port number.
        timeout: Max seconds to wait.

    Returns:
        True if connection succeeded, False otherwise.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _check_dev_server(timeout: float = 1.0) -> str:
    """Check if the FastAPI dev server is running by probing GET /health.

    Args:
        timeout: Max seconds to wait for the HTTP response.

    Returns:
        Status string for display.
    """
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            resp = client.get("http://127.0.0.1:8000/health")
            if resp.status_code < 500:
                return "[green]✅ Running[/green] [dim](http://127.0.0.1:8000)[/dim]"
            return "[yellow]⚠️  Unhealthy[/yellow]"
    except Exception:
        return "[dim]⏸️ Not running[/dim]"


def _pending_migrations(output_root: Path) -> str:
    """Detect whether Alembic migrations are pending.

    Args:
        output_root: The project output root directory.

    Returns:
        Status string for display.
    """
    alembic_dir = output_root / "alembic"
    if not alembic_dir.exists():
        return "[yellow]⚠️  Not initialized[/yellow]"
    versions_dir = alembic_dir / "versions"
    if not versions_dir.exists() or not list(versions_dir.glob("*.py")):
        return "[dim]No revisions yet[/dim]"
    return "[green]✅ Initialized[/green]"


def _last_action() -> str:
    """Read the most recent command from .kaira/history.jsonl.

    Returns:
        Display string of the last command, or 'None'.
    """
    history_path = Path.cwd() / ".kaira" / "history.jsonl"
    if not history_path.exists():
        return "[dim]None[/dim]"
    try:
        lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            record = json.loads(lines[-1])
            cmd = record.get("command", "unknown")
            ts = record.get("timestamp", "")[:19].replace("T", " ")
            return f"[cyan]{cmd}[/cyan] [dim]{ts}[/dim]"
    except Exception:
        pass
    return "[dim]None[/dim]"


@app.callback(invoke_without_command=True)
def status_main(ctx: typer.Context) -> None:
    """Show a live snapshot of the Kaira project status."""
    if ctx.invoked_subcommand is None:
        status_command()


def status_command() -> None:
    """Display a live project status snapshot.

    Shows: project/env info, DB connection, pending migrations,
    dev server status, model/route counts, auth status, last action.
    """
    from kaira.config import find_config_path, KairaConfig

    config_path = find_config_path()
    if not config_path.exists():
        console.print(
            Panel(
                "[yellow]No .kaira.json found. Run [bold]kaira init <name>[/bold] first.[/yellow]",
                border_style="yellow",
            )
        )
        return

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        cfg = KairaConfig.from_dict(raw)
    except Exception:
        raw = {}
        cfg = KairaConfig()

    project_name = raw.get("project", raw.get("project_name", Path.cwd().name))
    db_type = raw.get("database", cfg.db_type)
    auth_type = raw.get("auth", cfg.auth_type)
    app_env = os.environ.get("APP_ENV", "development")
    output_root = Path.cwd() / cfg.output_dir

    # DB probe
    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    if db_type == "sqlite":
        db_conn = "[green]✅ SQLite (local)[/green]"
    else:
        port = port_map.get(db_type, 0)
        db_conn = (
            "[green]✅ Reachable[/green]"
            if port and _ping_host("localhost", port, timeout=1.0)
            else "[red]❌ Unreachable[/red]"
        )

    # Resolved online/offline mode (Phase 6, Feature 4) — from the single source
    # in .kaira.json, never re-probed here.
    db_name = raw.get("db_name", "") or cfg.db_name
    db_mode = raw.get("db_mode", "") or cfg.db_mode or "online"
    if db_mode == "offline":
        mode_badge = "[bold yellow]⚠️ offline (SQLite)[/bold yellow]"
    else:
        mode_badge = "[bold green]✅ online[/bold green]"

    # Counts
    models_dir = output_root / cfg.models_dir
    routers_dir = output_root / cfg.routers_dir
    model_count = len(list(models_dir.glob("*.py"))) if models_dir.exists() else 0
    router_count = len(list(routers_dir.glob("*_router.py"))) if routers_dir.exists() else 0

    # Auth status
    auth_dir = output_root / "auth"
    auth_status = (
        "[green]✅ Configured[/green]"
        if (auth_dir / "dependencies.py").exists()
        else "[red]❌ Not set up[/red]"
    )

    # Migrations
    if db_type == "mongodb":
        mig_status = "[dim]N/A (MongoDB)[/dim]"
    else:
        mig_status = _pending_migrations(output_root)

    # Dev server
    dev_server = _check_dev_server(timeout=1.0)

    table = Table(title=f"⚡ Kaira Status — {project_name}", border_style="cyan")
    table.add_column("Property", style="dim", no_wrap=True)
    table.add_column("Value")

    table.add_row("Project", f"[bold]{project_name}[/bold]")
    table.add_row("Environment", f"[bold]{app_env}[/bold]")
    db_label = f"[bold]{db_type}[/bold]"
    if db_name:
        db_label += f" [dim]·[/dim] {db_name}"
    table.add_row("Database", f"{db_label}  [dim]·[/dim]  {mode_badge}  {db_conn}")
    table.add_row("Auth", f"[bold]{auth_type}[/bold]  {auth_status}")
    table.add_row("Migrations", mig_status)
    table.add_row("Dev Server", dev_server)
    table.add_row("Models", str(model_count))
    table.add_row("Routers", str(router_count))
    table.add_row("Last Action", _last_action())

    console.print(table)
