"""Kaira task command group — Celery background task scaffolding.

Generates tasks/<TaskName>.py with retry config, beat schedule registration,
and safe logging (task arguments are never logged to avoid PII/secrets exposure).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Celery background task scaffolding.")

_SNAKE_RE = re.compile(r"(?<!^)(?=[A-Z])")


def _pascal_to_snake(name: str) -> str:
    """Convert PascalCase to snake_case."""
    return _SNAKE_RE.sub("_", name).lower()


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _update_env_files(key: str, value: str) -> None:
    """Add or replace a key=value pair in all .env* files."""
    for env_file in Path.cwd().glob(".env*"):
        if env_file.is_dir():
            continue
        try:
            content = env_file.read_text(encoding="utf-8")
            if f"{key}=" in content:
                content = re.sub(
                    rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE
                )
            else:
                content += f"\n{key}={value}\n"
            env_file.write_text(content, encoding="utf-8")
        except OSError:
            pass


@app.command("init")
def task_init() -> None:
    """Initialise Celery for this project."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    tasks_dir = output_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "__init__.py").touch(exist_ok=True)

    celery_app_path = tasks_dir / "celery_app.py"
    if not celery_app_path.exists():
        jinja = _get_env_loader()
        tmpl = jinja.get_template("celery_app.py.j2")
        celery_app_path.write_text(
            tmpl.render(project_name=Path.cwd().name, scheduled_tasks=[]),
            encoding="utf-8",
        )
        console.print(f"  [green]✅[/green] Generated: [cyan]{celery_app_path}[/cyan]")

    _update_env_files("CELERY_BROKER_URL", "redis://localhost:6379/0")
    _update_env_files("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    console.print(
        "  [green]✅[/green] CELERY_BROKER_URL + CELERY_RESULT_BACKEND added to .env* files"
    )

    settings_candidates = [
        output_root / "core" / "config.py",
        output_root / "config" / "settings.py",
    ]
    for settings_path in settings_candidates:
        if settings_path.exists():
            content = settings_path.read_text(encoding="utf-8")
            if "CELERY_BROKER_URL" not in content:
                content = content.rstrip() + (
                    '\n    CELERY_BROKER_URL: str = "redis://localhost:6379/0"'
                    '\n    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"\n'
                )
                settings_path.write_text(content, encoding="utf-8")
                console.print(
                    f"  [green]✅[/green] Celery settings added to {settings_path.name}"
                )
            break

    console.print(
        Panel(
            "[green]✅ Celery initialised.[/green]\n"
            "Next: [cyan]kaira task generate <TaskName>[/cyan] to create a task.",
            border_style="green",
        )
    )


@app.command("generate")
def task_generate(
    task_name: Annotated[
        str, typer.Argument(help="PascalCase task class name, e.g. SendEmail")
    ],
    schedule: Annotated[
        Optional[str],
        typer.Option(
            "--schedule", help="Cron schedule, e.g. crontab(minute=0, hour='*')"
        ),
    ] = None,
) -> None:
    """Generate a Celery task class."""
    if not task_name[0].isupper():
        console.print("[red]❌ Task name must be PascalCase, e.g. SendEmail[/red]")
        raise typer.Exit(1)

    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    tasks_dir = output_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    snake = _pascal_to_snake(task_name)
    task_path = tasks_dir / f"{snake}.py"

    jinja = _get_env_loader()
    tmpl = jinja.get_template("celery_task.py.j2")
    task_path.write_text(
        tmpl.render(task_name=task_name, snake_name=snake),
        encoding="utf-8",
    )
    console.print(f"  [green]✅[/green] Generated: [cyan]{task_path}[/cyan]")

    if schedule:
        celery_app_path = tasks_dir / "celery_app.py"
        if celery_app_path.exists():
            content = celery_app_path.read_text(encoding="utf-8")
            beat_entry = (
                f'        "{snake}": {{\n'
                f'            "task": "tasks.{snake}.{snake}_task",\n'
                f'            "schedule": {schedule},\n'
                f"        }},\n"
            )
            content = content.replace("    },\n)", f"    {beat_entry}    }},\n)")
            celery_app_path.write_text(content, encoding="utf-8")
            console.print(
                f"  [green]✅[/green] Registered in beat_schedule: [cyan]{snake}[/cyan]"
            )

    console.print(
        Panel(
            f"[green]✅ Task [bold]{task_name}[/bold] generated at tasks/{snake}.py[/green]\n"
            f"Run with: [cyan]kaira task run {task_name}[/cyan]",
            border_style="green",
        )
    )


@app.command("list")
def task_list() -> None:
    """List all generated Celery task files."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    tasks_dir = output_root / "tasks"

    if not tasks_dir.exists():
        console.print(
            "[yellow]No tasks/ directory found. Run kaira task init first.[/yellow]"
        )
        return

    task_files = [
        f
        for f in tasks_dir.glob("*.py")
        if f.name not in {"__init__.py", "celery_app.py"}
    ]
    if not task_files:
        console.print(
            "[dim]No tasks generated yet. Use kaira task generate <TaskName>.[/dim]"
        )
        return

    table = Table(title="⚡ Celery Tasks", border_style="cyan")
    table.add_column("File", style="cyan")
    table.add_column("Class Name", style="bold")
    for f in sorted(task_files):
        class_name = "".join(word.capitalize() for word in f.stem.split("_"))
        table.add_row(str(f.name), class_name)
    console.print(table)


@app.command("run")
def task_run(
    task_name: Annotated[str, typer.Argument(help="PascalCase task name to run")],
) -> None:
    """Run a Celery task immediately via celery call."""
    snake = _pascal_to_snake(task_name)
    task_module = f"tasks.{snake}.{snake}_task"

    if not shutil.which("celery"):
        console.print(
            Panel(
                "[yellow]celery not found in PATH.\n"
                "Install with: pip install celery[redis][/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    console.print(f"[cyan]Running task: {task_module}...[/cyan]")
    subprocess.run(["celery", "call", task_module])


@app.command("monitor")
def task_monitor() -> None:
    """Open the Celery Flower monitoring dashboard."""
    if not shutil.which("celery"):
        console.print(
            Panel(
                "[yellow]celery not found in PATH.\nInstall with: pip install celery[redis][/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    console.print("[cyan]Starting Celery Flower monitor...[/cyan]")
    console.print("[dim]Dashboard will be available at http://localhost:5555[/dim]")
    try:
        subprocess.run(["celery", "-A", "tasks.celery_app", "flower"])
    except FileNotFoundError:
        console.print(
            Panel(
                "[yellow]flower not found.\nInstall with: pip install flower[/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)
