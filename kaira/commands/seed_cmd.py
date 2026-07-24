"""Database seeding command group."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm

from kaira.config import get_config
from kaira.console import console
from kaira.core.detector import write_with_check
from kaira.core.parser import camel_to_snake

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Database seeding commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("generate")
def seed_generate(
    model_name: Annotated[str, typer.Argument(help="Name of the model to generate a seed file for.")],
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Generate a mock data seed script for a model."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    seeds_dir = output_root / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    (seeds_dir / "__init__.py").touch(exist_ok=True)

    # Find the model details in config
    model_entry = next((m for m in config.generated_models if m.get("name") == model_name), None)
    fields = model_entry.get("fields", []) if model_entry else []

    env = _get_env()
    snake = camel_to_snake(model_name)
    ctx = {
        "model_name": model_name,
        "snake_name": snake,
        "fields": fields,
        "models_dir": config.models_dir,
    }

    tmpl = env.get_template("seed_model.py.j2")
    out_path = seeds_dir / f"seed_{snake}.py"
    write_with_check(out_path, tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")


@app.command("run")
def seed_run(
    model_name: Annotated[Optional[str], typer.Argument(help="Name of the model to seed.")] = None,
    seed_all: Annotated[bool, typer.Option("--all", help="Run all seed scripts.")] = False,
) -> None:
    """Run database seed scripts (development/staging only)."""
    # Enforce settings APP_ENV safety check
    # We dynamically load Settings or read .env to check environment
    # Since settings.py is under config/settings.py in output, we can check it
    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production":
        console.print("[red]Error: Seeding is disabled in production to protect data![/red]")
        raise typer.Exit(1)

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    seeds_dir = output_root / "seeds"

    if not seeds_dir.exists():
        console.print("[yellow]No seeds directory found. Run kaira seed generate <Model> first.[/yellow]")
        return

    scripts = []
    if seed_all:
        scripts = list(seeds_dir.glob("seed_*.py"))
    elif model_name:
        snake = camel_to_snake(model_name)
        target = seeds_dir / f"seed_{snake}.py"
        if not target.exists():
            console.print(f"[red]Seed script not found:[/red] {target}")
            raise typer.Exit(1)
        scripts = [target]
    else:
        console.print("[red]Error: Must specify either a model name or --all[/red]")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Running seeds...", total=len(scripts))
        for script in scripts:
            progress.update(task, description=f"[cyan]  {script.name}...")
            try:
                from kaira.config import get_venv_python
                python_exe = get_venv_python()
                env = os.environ.copy()
                env["PYTHONPATH"] = str(output_root) + os.pathsep + env.get("PYTHONPATH", "")
                subprocess.run([python_exe, str(script)], check=True, env=env)
                console.print(f"  [green bold]✓[/green bold]  Seeded successfully: {script.name}")
            except Exception as e:
                console.print(f"[red]Error seeding {script.name}: {e}[/red]")
                raise typer.Exit(1)
            progress.advance(task)


@app.command("clear")
def seed_clear() -> None:
    """Clear all data from generated database tables (requires confirmation)."""
    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production":
        console.print("[red]Error: Database clearing is disabled in production![/red]")
        raise typer.Exit(1)

    confirm = Confirm.ask("[yellow]⚠  Are you sure you want to clear all data from database tables?[/yellow]")
    if not confirm:
        console.print("Operation cancelled.")
        return

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    
    # We dynamically load and drop tables, or run sql clear
    # Let's run a simple python script to drop and recreate all tables
    console.print("[cyan]Clearing database tables...[/cyan]")
    clear_script = (
        "from database import engine, Base\n"
        "Base.metadata.reflect(bind=engine)\n"
        "Base.metadata.drop_all(bind=engine)\n"
        "Base.metadata.create_all(bind=engine)\n"
        "print('Database tables cleared and recreated successfully.')\n"
    )
    
    try:
        from kaira.config import get_venv_python
        python_exe = get_venv_python()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(output_root) + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run([python_exe, "-c", clear_script], check=True, env=env)
        console.print("[green]✔ Database cleared successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error clearing database: {e}[/red]")
        raise typer.Exit(1)
