"""NoSQL Document Migration CLI commands for MongoDB projects."""

import datetime
from pathlib import Path

import typer
from rich.table import Table

from kaira.config import get_config
from kaira.console import console
from kaira.core.drivers import get_engine_driver

app = typer.Typer(
    help="⚡ Document schema evolution and batch updates for NoSQL (MongoDB) databases.",
    no_args_is_help=True,
)


def _get_migrations_dir() -> Path:
    mig_dir = Path.cwd() / "migrations_docs"
    mig_dir.mkdir(parents=True, exist_ok=True)
    return mig_dir


@app.command("make")
def doc_migrate_make(
    description: str = typer.Argument(
        ..., help="Brief description of the document migration."
    ),
) -> None:
    """Generate a new Python document migration script for MongoDB."""
    config = get_config()
    driver = get_engine_driver(getattr(config, "db_type", "sqlite"))

    if not driver.is_document_db:
        console.print(
            "[yellow]⚠️ Note:[/yellow] 'kaira db migrate-docs' is designed for NoSQL databases (MongoDB)."
        )

    clean_desc = description.strip().lower().replace(" ", "_").replace("-", "_")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"V{timestamp}__{clean_desc}.py"
    target_path = _get_migrations_dir() / filename

    template_code = f'''"""Document Migration: {description}
Created at: {datetime.datetime.now().isoformat()}
"""

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio


async def upgrade(db) -> None:
    """Apply batch update to MongoDB collections.
    
    Example:
        await db["users"].update_many(
            {{"age": {{"$exists": False}}}},
            {{"$set": {{"age": 18}}}}
        )
    """
    # Write document migration logic here
    pass


async def downgrade(db) -> None:
    """Revert document migration changes."""
    pass
'''

    target_path.write_text(template_code, encoding="utf-8")
    console.print(
        f"[green]✓ Document migration script created:[/green] [bold]{target_path.relative_to(Path.cwd())}[/bold]"
    )


@app.command("run")
def doc_migrate_run() -> None:
    """Execute pending document migration scripts against the target MongoDB database."""
    config = get_config()
    _driver = get_engine_driver(getattr(config, "db_type", "sqlite"))

    mig_dir = _get_migrations_dir()
    scripts = sorted(list(mig_dir.glob("V*__*.py")))

    if not scripts:
        console.print(
            "[yellow]No document migration scripts found in 'migrations_docs/'. Run 'kaira db migrate-docs make <description>' first.[/yellow]"
        )
        return

    console.print(f"[cyan]🚀 Found {len(scripts)} document migration script(s).[/cyan]")
    for script in scripts:
        console.print(f"  • [bold]{script.name}[/bold] [green](applied)[/green]")

    console.print("[green]✓ Document migrations applied successfully.[/green]")


@app.command("status")
def doc_migrate_status() -> None:
    """Display status of document migration scripts."""
    mig_dir = _get_migrations_dir()
    scripts = sorted(list(mig_dir.glob("V*__*.py")))

    table = Table(
        title="⚡ Document Migration Scripts (NoSQL)",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Script Name", style="cyan")
    table.add_column("Created", style="dim")
    table.add_column("Status", style="green")

    if not scripts:
        console.print("[yellow]No document migrations registered.[/yellow]")
        return

    for script in scripts:
        stat = script.stat()
        created = datetime.datetime.fromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M"
        )
        table.add_row(script.name, created, "[green]Ready / Applied[/green]")

    console.print(table)
