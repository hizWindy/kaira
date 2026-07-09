"""DevFlow db command group — database connection, management, and utilities."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from devflow.console import console
from devflow.commands.ux_helpers import mask_credentials, typed_confirmation

app = typer.Typer(help="Database connection, status, and management commands.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DB_CLIENTS: dict[str, str] = {
    "postgresql": "psql",
    "mysql": "mysql",
    "mongodb": "mongosh",
    "sqlite": "sqlite3",
}

_DB_DRIVERS: dict[str, list[str]] = {
    "postgresql": ["asyncpg", "sqlalchemy[asyncio]"],
    "mysql": ["aiomysql", "sqlalchemy[asyncio]"],
    "mongodb": ["motor", "beanie"],
    "sqlite": ["aiosqlite", "sqlalchemy[asyncio]"],
}

_RELATIONAL = {"postgresql", "mysql", "sqlite"}


def _get_database_url() -> str:
    """Read DATABASE_URL from environment, masking credentials for display.

    Returns:
        Masked connection URL string.
    """
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        # Try reading from .env
        env_file = Path.cwd() / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return raw


def _get_db_type_from_config() -> str:
    """Read db_type from .devflow.json or fallback to env URL inspection.

    Returns:
        Database type string, e.g. 'postgresql'.
    """
    try:
        from devflow.config import get_config
        cfg = get_config()
        return cfg.db_type
    except Exception:
        url = _get_database_url()
        for db in ("postgresql", "mysql", "mongodb", "sqlite"):
            if db in url.lower():
                return db
        return "unknown"


def _update_env_files(key: str, value: str) -> None:
    """Set a key=value pair in all .env* files in the current directory.

    Args:
        key: Environment variable name.
        value: Value to set (if already present, line is replaced).
    """
    env_files = list(Path.cwd().glob(".env*"))
    for env_file in env_files:
        if env_file.is_dir():
            continue
        try:
            content = env_file.read_text(encoding="utf-8")
            if f"{key}=" in content:
                content = re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE)
            else:
                content += f"\n{key}={value}\n"
            env_file.write_text(content, encoding="utf-8")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("connect")
def db_connect() -> None:
    """Test the database connection using the configured DATABASE_URL."""
    raw_url = _get_database_url()
    if not raw_url:
        console.print(
            Panel(
                "[red]DATABASE_URL not set.\nAdd it to your .env file or export it.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    masked = mask_credentials(raw_url)
    console.print(f"[cyan]Connecting to:[/cyan] {masked}")

    db_type = _get_db_type_from_config()
    import socket

    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    if db_type == "sqlite":
        console.print(Panel("[green]✅ SQLite — no connection test needed.[/green]", border_style="green"))
        return

    port = port_map.get(db_type, 0)
    host = "localhost"
    m = re.search(r"@([^:/]+)[:/]", raw_url)
    if m:
        host = m.group(1)

    try:
        with socket.create_connection((host, port), timeout=5.0):
            console.print(Panel(f"[green]✅ Connected to {db_type} at {host}:{port}[/green]", border_style="green"))
    except Exception as exc:
        console.print(
            Panel(f"[red]❌ Connection failed: {exc}\nURL: {masked}[/red]", border_style="red")
        )
        raise typer.Exit(1)


@app.command("status")
def db_status() -> None:
    """Show database configuration and connection status."""
    db_type = _get_db_type_from_config()
    raw_url = _get_database_url()
    masked = mask_credentials(raw_url) if raw_url else "[dim]DATABASE_URL not set[/dim]"

    table = Table(title="⚡ DevFlow — DB Status", border_style="cyan")
    table.add_column("Property", style="dim")
    table.add_column("Value")
    table.add_row("DB Type", f"[bold]{db_type}[/bold]")
    table.add_row("URL", masked)

    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    if db_type == "sqlite":
        table.add_row("Connection", "[green]✅ SQLite (local file)[/green]")
    elif db_type in port_map and raw_url:
        import socket

        host = "localhost"
        m = re.search(r"@([^:/]+)[:/]", raw_url)
        if m:
            host = m.group(1)
        try:
            with socket.create_connection((host, port_map[db_type]), timeout=2.0):
                table.add_row("Connection", "[green]✅ Reachable[/green]")
        except Exception:
            table.add_row("Connection", "[red]❌ Unreachable[/red]")
    else:
        table.add_row("Connection", "[dim]Not tested[/dim]")

    console.print(table)


@app.command("reset")
def db_reset(
    force: Annotated[bool, typer.Option("--force", help="Skip typed confirmation (CI mode)")] = False,
) -> None:
    """Drop and recreate the database (DESTRUCTIVE). Blocked in production.

    Args:
        force: Bypass typed confirmation for CI use.
    """
    db_type = _get_db_type_from_config()
    if not typed_confirmation("reset", "This will DROP and RECREATE the database. All data will be lost.", force=force):
        return

    if db_type == "mongodb":
        console.print("[yellow]MongoDB reset: drop and recreate the database manually via mongosh.[/yellow]")
        return

    console.print(
        Panel(
            "[yellow]⚠️  Database reset requires running Alembic downgrade + upgrade.\n"
            "Run:\n"
            "  alembic downgrade base\n"
            "  alembic upgrade head[/yellow]",
            border_style="yellow",
        )
    )


@app.command("shell")
def db_shell() -> None:
    """Open an interactive database shell (psql / mysql / mongosh / sqlite3)."""
    db_type = _get_db_type_from_config()
    client = _DB_CLIENTS.get(db_type)

    if not client:
        console.print(f"[red]Unknown database type: {db_type}[/red]")
        raise typer.Exit(1)

    if not shutil.which(client):
        console.print(
            Panel(
                f"[yellow]'{client}' not found in PATH.\n"
                f"Install the {db_type} client to use this command.[/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    raw_url = _get_database_url()
    cmd = [client]
    if raw_url and db_type != "sqlite":
        cmd.append(mask_credentials(raw_url).replace("***:***@", ":@"))  # best-effort
        # Actually pass original URL (not masked) to the real client
        cmd = [client, raw_url] if db_type != "mongodb" else [client, raw_url]

    console.print(f"[cyan]Launching {client}...[/cyan]")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


@app.command("backup")
def db_backup(
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output directory for backup file"),
    ] = None,
) -> None:
    """Backup the database to a dump file.

    Args:
        output: Directory to write the backup to (default: current directory).
    """
    import datetime

    db_type = _get_db_type_from_config()
    out_dir = Path(output) if output else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"backup_{db_type}_{timestamp}.dump"

    tool_map = {"postgresql": "pg_dump", "mysql": "mysqldump"}
    tool = tool_map.get(db_type)

    if db_type == "sqlite":
        raw_url = _get_database_url()
        db_path_match = re.search(r"sqlite(?:\+aiosqlite)?:///(.+)", raw_url or "")
        db_path = db_path_match.group(1) if db_path_match else "./app.db"
        import shutil as _sh
        _sh.copy2(db_path, str(out_file).replace(".dump", ".db"))
        console.print(f"[green]✅ SQLite backup saved: {out_file.with_suffix('.db')}[/green]")
        return

    if db_type == "mongodb":
        if not shutil.which("mongodump"):
            console.print("[yellow]mongodump not found. Install MongoDB Database Tools.[/yellow]")
            raise typer.Exit(1)
        subprocess.run(["mongodump", "--out", str(out_dir / f"backup_{timestamp}")])
        console.print(f"[green]✅ MongoDB backup saved: {out_dir / f'backup_{timestamp}'}[/green]")
        return

    if not tool or not shutil.which(tool):
        console.print(f"[yellow]{tool or 'backup tool'} not found. Install the {db_type} client tools.[/yellow]")
        raise typer.Exit(1)

    raw_url = _get_database_url()
    subprocess.run([tool, raw_url, "-f", str(out_file)])
    console.print(f"[green]✅ Backup saved: {out_file}[/green]")


@app.command("restore")
def db_restore(
    file: Annotated[str, typer.Argument(help="Path to backup file to restore")],
    force: Annotated[bool, typer.Option("--force", help="Skip typed confirmation")] = False,
) -> None:
    """Restore the database from a backup file. Blocked in production.

    Args:
        file: Path to the backup dump file.
        force: Bypass typed confirmation for CI use.
    """
    if not typed_confirmation("restore", f"This will RESTORE the database from '{file}'. Current data will be overwritten.", force=force):
        return

    backup_path = Path(file)
    if not backup_path.exists():
        console.print(f"[red]Backup file not found: {file}[/red]")
        raise typer.Exit(1)

    db_type = _get_db_type_from_config()
    tool_map = {"postgresql": "psql", "mysql": "mysql"}
    tool = tool_map.get(db_type)

    if db_type == "sqlite":
        raw_url = _get_database_url()
        db_path_match = re.search(r"sqlite(?:\+aiosqlite)?:///(.+)", raw_url or "")
        db_path = db_path_match.group(1) if db_path_match else "./app.db"
        import shutil as _sh
        _sh.copy2(file, db_path)
        console.print(f"[green]✅ SQLite restored from {file}[/green]")
        return

    if not tool or not shutil.which(tool):
        console.print(f"[yellow]{tool or 'restore tool'} not found.[/yellow]")
        raise typer.Exit(1)

    raw_url = _get_database_url()
    subprocess.run([tool, raw_url, "-f", file])
    console.print(f"[green]✅ Database restored from {file}[/green]")


@app.command("switch")
def db_switch(
    db_type: Annotated[
        str,
        typer.Argument(help="New database type: postgresql | mysql | mongodb | sqlite"),
    ],
) -> None:
    """Switch the project's database type. Updates .devflow.json and .env files.

    Args:
        db_type: Target database type.
    """
    valid = {"postgresql", "mysql", "mongodb", "sqlite"}
    if db_type not in valid:
        from devflow.commands.smart_errors import smart_error
        smart_error(
            context=f"Unknown database type: {db_type}",
            typed=db_type,
            candidates=list(valid),
            guide_topic="db",
        )

    try:
        from devflow.config import get_config, save_config
        cfg = get_config()
        old_type = cfg.db_type
    except Exception:
        old_type = "unknown"

    # Warn on relational ↔ MongoDB switch
    old_is_relational = old_type in _RELATIONAL
    new_is_relational = db_type in _RELATIONAL
    if old_is_relational != new_is_relational:
        console.print(
            Panel(
                f"[yellow]⚠️  Switching from [bold]{old_type}[/bold] to [bold]{db_type}[/bold] "
                f"is a BREAKING change.\n"
                f"Generated model and repository files will need to be regenerated.\n"
                f"Run [bold]devflow generate model <Name>[/bold] after switching.[/yellow]",
                border_style="yellow",
            )
        )

    # Update .devflow.json
    try:
        from devflow.config import get_config, save_config
        cfg = get_config()
        cfg.db_type = db_type
        save_config(cfg)
        console.print(f"[green]✅ .devflow.json updated: db_type = {db_type}[/green]")
    except Exception as exc:
        console.print(f"[yellow]Could not update .devflow.json: {exc}[/yellow]")

    # Update DATABASE_URL placeholder in .env files
    url_map = {
        "postgresql": "postgresql+asyncpg://user:password@localhost/mydb",
        "mysql": "mysql+aiomysql://user:password@localhost/mydb",
        "mongodb": "mongodb://localhost:27017/mydb",
        "sqlite": "sqlite+aiosqlite:///./app.db",
    }
    _update_env_files("DATABASE_URL", url_map[db_type])
    console.print(f"[green]✅ DATABASE_URL placeholder updated in .env files[/green]")

    # Install driver
    drivers = _DB_DRIVERS.get(db_type, [])
    if drivers:
        from devflow.commands.project import install_packages
        install_packages(drivers)

    console.print(
        Panel(
            f"[green]✅ Switched to [bold]{db_type}[/bold].\n"
            f"Update DATABASE_URL in your .env files with real credentials.",
            border_style="green",
        )
    )


@app.command("benchmark")
def db_benchmark() -> None:
    """Run a basic connection and query timing benchmark."""
    import time

    db_type = _get_db_type_from_config()
    raw_url = _get_database_url()
    masked = mask_credentials(raw_url) if raw_url else "[dim]not set[/dim]"

    console.print(f"[cyan]Benchmarking {db_type} connection...[/cyan]")
    console.print(f"[dim]URL: {masked}[/dim]\n")

    if db_type == "sqlite":
        # Simple file I/O benchmark
        start = time.perf_counter()
        import sqlite3 as _sqlite3
        raw_path = re.search(r"sqlite(?:\+aiosqlite)?:///(.+)", raw_url or "") 
        db_path = raw_path.group(1) if raw_path else ":memory:"
        conn = _sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        elapsed = (time.perf_counter() - start) * 1000
        console.print(f"[green]✅ SQLite query: {elapsed:.2f}ms[/green]")
        return

    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    port = port_map.get(db_type, 0)
    host = "localhost"
    m = re.search(r"@([^:/]+)[:/]", raw_url or "")
    if m:
        host = m.group(1)

    if not port:
        console.print("[yellow]Cannot benchmark unknown database type.[/yellow]")
        return

    import socket

    times = []
    for i in range(5):
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=2.0):
                pass
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        except Exception:
            console.print(f"[red]Connection {i+1}: failed[/red]")

    if times:
        avg = sum(times) / len(times)
        mn = min(times)
        mx = max(times)
        table = Table(title=f"Benchmark Results — {db_type}", border_style="cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Samples", str(len(times)))
        table.add_row("Avg", f"{avg:.2f}ms")
        table.add_row("Min", f"{mn:.2f}ms")
        table.add_row("Max", f"{mx:.2f}ms")
        console.print(table)
    else:
        console.print("[red]❌ All connections failed.[/red]")
        raise typer.Exit(1)
