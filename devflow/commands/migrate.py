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


# Database types that are schemaless and therefore have no Alembic path.
_NON_RELATIONAL_DB_TYPES = {"mongodb", "atlas", "firebase", "firestore"}


def _guard_relational_db() -> None:
    """Block migration commands on MongoDB / Atlas / Firestore projects.

    Alembic only applies to relational databases.  Document stores are
    schemaless, so any ``migrate`` subcommand must short-circuit here — before
    Alembic is touched or the ``models/`` package is walked — with the Phase 4
    smart-error format.

    Raises:
        typer.Exit: Always, when the project's database is non-relational.
    """
    try:
        from devflow.config import get_config

        db_type = get_config().db_type.lower()
    except Exception:
        return  # No/invalid config — let the normal Alembic path handle it.

    if db_type in _NON_RELATIONAL_DB_TYPES:
        from devflow.commands.smart_errors import error_migrate_on_document_db

        error_migrate_on_document_db(db_type)


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
    _guard_relational_db()
    cwd = Path.cwd()
    console.print(
        Panel(
            f"Initializing Alembic in [cyan]{cwd}[/cyan]",
            title="[bold]DevFlow[/bold] — Migrate Init",
            border_style="cyan",
        )
    )
    _run_alembic(["init", "alembic"], cwd)

    # Overwrite env.py with a fully pre-configured, zero-config dynamic version
    env_path = cwd / "alembic" / "env.py"
    if env_path.exists():
        env_content = """import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add project root to python path so settings and core can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import settings
from core.database import Base

# Dynamically import all modules under models package so they register with Base.metadata
try:
    import importlib
    import pkgutil
    import models
    for _, module_name, _ in pkgutil.walk_packages(models.__path__, models.__name__ + "."):
        importlib.import_module(module_name)
except Exception:
    pass

# this is the Alembic Config object, which provides access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata
target_metadata = Base.metadata

# Set database URL dynamically from project settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def run_migrations_offline() -> None:
    \"\"\"Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DB API to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    \"\"\"
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    \"\"\"Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    \"\"\"
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
"""
        env_path.write_text(env_content, encoding="utf-8")
        console.print(
            "[bold green]✓[/bold green]  Alembic env.py automatically pre-configured for async RDBMS and models."
        )
    else:
        console.print(
            "[yellow]⚠[/yellow]  Could not find generated alembic/env.py file to pre-configure."
        )


def _ensure_alembic_initialized() -> Path:
    """Ensure alembic.ini is present in the current working directory.

    If not, automatically runs migrate_init() to initialize it.
    """
    cwd = Path.cwd()
    ini_path = cwd / "alembic.ini"
    env_path = cwd / "alembic" / "env.py"
    if not ini_path.exists() or not env_path.exists():
        console.print(
            "[bold yellow]⚠️  Alembic not initialized — initializing automatically...[/bold yellow]"
        )
        migrate_init()
    return ini_path


@app.command("make")
def migrate_make(
    message: Annotated[
        str, typer.Argument(help='Migration message, e.g. "add user table"')
    ],
) -> None:
    """Generate a new Alembic migration.

    Runs: alembic revision --autogenerate -m MESSAGE
    """
    _guard_relational_db()
    ini_path = _ensure_alembic_initialized()
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
    _guard_relational_db()
    ini_path = _ensure_alembic_initialized()
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
    _guard_relational_db()
    ini_path = _ensure_alembic_initialized()
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
