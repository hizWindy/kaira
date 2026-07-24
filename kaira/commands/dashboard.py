"""Welcome dashboard for Kaira CLI — shown when kaira is run with no arguments."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Optional

from rich.columns import Columns
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devflow.console import console


# ---------------------------------------------------------------------------
# Connection probe helpers
# ---------------------------------------------------------------------------


def _probe_db(db_type: str, timeout: float = 2.0) -> str:
    """Attempt a lightweight TCP connection check for the configured database.

    Args:
        db_type: One of postgresql, mysql, mongodb, sqlite.
        timeout: Maximum seconds to wait for the connection.

    Returns:
        A short status string for display.
    """
    if db_type == "sqlite":
        return "[green]✅ SQLite (local)[/green]"

    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    port = port_map.get(db_type)
    if port is None:
        return "[dim]Unknown[/dim]"

    # Read DATABASE_URL from env to get host, fallback to localhost
    raw_url = os.environ.get("DATABASE_URL", "")
    host = "localhost"
    if raw_url:
        import re

        m = re.search(r"@([^:/]+)[:/]", raw_url)
        if m:
            host = m.group(1)

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "[green]✅ Connected[/green]"
    except (OSError, socket.timeout):
        return "[red]❌ Unreachable[/red]"
    except Exception:
        return "[yellow]⏱️ Timeout[/yellow]"


def _count_files(directory: Path, pattern: str) -> int:
    """Count files matching a glob pattern in a directory.

    Args:
        directory: Directory to scan.
        pattern: Glob pattern.

    Returns:
        Number of matching files (0 if directory does not exist).
    """
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def _last_action() -> str:
    """Read the most recent command from .devflow/history.jsonl.

    Returns:
        Short display string of the last command, or 'None'.
    """
    history_path = Path.cwd() / ".devflow" / "history.jsonl"
    if not history_path.exists():
        return "[dim]None[/dim]"
    try:
        lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            record = json.loads(lines[-1])
            cmd = record.get("command", "unknown")
            ts = record.get("timestamp", "")[:10]
            return f"[cyan]{cmd}[/cyan] [dim]{ts}[/dim]"
    except Exception:
        pass
    return "[dim]None[/dim]"


# ---------------------------------------------------------------------------
# Dashboard renderers
# ---------------------------------------------------------------------------


def _render_inside_project(config_path: Path) -> None:
    """Render the full project dashboard.

    Args:
        config_path: Path to the .devflow.json file.
    """
    # Load raw config for fields not in DevFlowConfig dataclass
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        console.print(
            Panel(
                "[yellow]⚠️  .devflow.json is malformed or unreadable.\n"
                "Run [bold]kaira config show[/bold] to inspect it.[/yellow]",
                title="[yellow]Kaira — Config Warning[/yellow]",
                border_style="yellow",
            )
        )
        return

    from devflow.config import DevFlowConfig

    try:
        cfg = DevFlowConfig.from_dict(raw)
    except Exception:
        cfg = DevFlowConfig()

    project_name = raw.get("project", raw.get("project_name", Path.cwd().name))
    db_type = raw.get("database", cfg.db_type)
    auth_type = raw.get("auth", cfg.auth_type)
    has_docker = raw.get("docker", False)
    ci_platform = raw.get("ci", "none")
    api_version = raw.get("api_version", cfg.api_version)

    output_root = Path.cwd() / cfg.output_dir

    # Stats
    model_count = _count_files(output_root / cfg.models_dir, "*.py")
    router_count = _count_files(output_root / cfg.routers_dir, "*_router.py")
    test_count = _count_files(output_root / "tests", "test_*.py")

    # DB connection probe (non-blocking, 2s timeout)
    db_status = _probe_db(db_type, timeout=2.0)

    # Auth status
    auth_dir = output_root / "auth"
    auth_status = (
        "[green]✅ Configured[/green]"
        if (auth_dir / "dependencies.py").exists()
        else "[red]❌ Not set up[/red]"
    )

    # Docker status
    docker_status = (
        "[green]✅ Dockerfile present[/green]"
        if (output_root / "Dockerfile").exists()
        else "[dim]Not configured[/dim]"
    )

    # Pending migrations (only for relational DBs)
    if db_type == "mongodb":
        migration_status = "[dim]N/A (MongoDB)[/dim]"
    else:
        alembic_dir = output_root / "alembic"
        migration_status = (
            "[green]✅ Initialized[/green]"
            if alembic_dir.exists()
            else "[yellow]⚠️  Not initialized[/yellow]"
        )

    # Action-required items
    actions: list[str] = []
    if db_type != "mongodb" and not (output_root / "alembic").exists():
        actions.append("Run [bold cyan]kaira migrate init[/bold cyan] to set up migrations")
    if not (auth_dir / "dependencies.py").exists():
        actions.append("Run [bold cyan]kaira auth generate --type jwt[/bold cyan] to add auth")
    if not (output_root / "Dockerfile").exists():
        actions.append("Run [bold cyan]kaira docker init --with-compose[/bold cyan] to add Docker")
    if router_count > test_count:
        actions.append("Run [bold cyan]kaira test generate --all[/bold cyan] to generate tests")

    # ── Header
    console.print(
        Panel(
            f"[bold cyan]⚡ Kaira — {project_name}[/bold cyan]  "
            f"[dim]API {api_version}[/dim]",
            border_style="cyan",
            expand=True,
        )
    )

    # ── Info table
    info = Table.grid(padding=(0, 2))
    info.add_column(style="dim", no_wrap=True)
    info.add_column()
    info.add_row("Database", f"[bold]{db_type}[/bold]  {db_status}")
    info.add_row("Auth", f"[bold]{auth_type}[/bold]  {auth_status}")
    info.add_row("Docker", docker_status)
    info.add_row("CI/CD", f"[bold]{ci_platform}[/bold]")
    info.add_row("Migrations", migration_status)
    console.print(Panel(info, title="Project Info", border_style="blue", expand=False))

    # ── Stats table
    stats = Table.grid(padding=(0, 3))
    stats.add_column(style="dim")
    stats.add_column(style="bold")
    stats.add_row("Models", str(model_count))
    stats.add_row("Routers", str(router_count))
    stats.add_row("Tests", str(test_count))
    stats.add_row("Last action", _last_action())
    console.print(Panel(stats, title="Stats", border_style="blue", expand=False))

    # ── Action-required
    if actions:
        action_text = "\n".join(f"  • {a}" for a in actions)
        console.print(
            Panel(
                action_text,
                title="[yellow]⚠️  Action Required[/yellow]",
                border_style="yellow",
                expand=False,
            )
        )

    # ── Quick commands
    quick = (
        "[dim]Generate a model:[/dim]  [cyan]kaira generate model <Name> --fields \"field:type\"[/cyan]\n"
        "[dim]Run health check:[/dim]  [cyan]kaira health[/cyan]\n"
        "[dim]View all guides:[/dim]  [cyan]kaira guide[/cyan]\n"
        "[dim]Project status:[/dim]   [cyan]kaira status[/cyan]"
    )
    console.print(Panel(quick, title="Quick Commands", border_style="dim", expand=False))
    _print_attribution_footer()


def _render_outside_project() -> None:
    """Render the minimal welcome panel when outside a Kaira project."""
    from devflow import __version__

    content = (
        f"[bold cyan]Kaira[/bold cyan] v{__version__} — Automated FastAPI Scaffolding CLI\n\n"
        "Start a new project:\n"
        "  [bold cyan]kaira init <project-name>[/bold cyan]\n\n"
        "Browse guides:\n"
        "  [bold cyan]kaira guide[/bold cyan]\n\n"
        "[dim]No .devflow.json found in this directory.[/dim]"
    )
    console.print(
        Panel(
            content,
            title="[bold cyan]⚡ Welcome to Kaira[/bold cyan]",
            border_style="cyan",
            expand=False,
        )
    )
    _print_attribution_footer()


def _print_attribution_footer() -> None:
    """Print a single muted attribution line below the dashboard panels."""
    from devflow.core.theme import Theme, attribution, sym

    bolt = sym("BOLT")
    console.print(f"[{Theme.MUTED}]{bolt} Kaira · {attribution()}[/{Theme.MUTED}]")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def welcome_dashboard() -> None:
    """Render the Kaira welcome dashboard.

    Inside a project: full stats, connection status, action-required items.
    Outside a project: minimal welcome pointing to kaira init and kaira guide.
    Never blocks or crashes — all errors handled gracefully.
    """
    from devflow.config import find_config_path

    try:
        config_path = find_config_path()
        if config_path.exists():
            _render_inside_project(config_path)
        else:
            _render_outside_project()
    except Exception as exc:
        # Last-resort fallback — never crash
        console.print(
            Panel(
                f"[yellow]⚠️  Dashboard error: {exc}\n"
                "Run [bold]kaira config show[/bold] for more info.[/yellow]",
                border_style="yellow",
            )
        )
