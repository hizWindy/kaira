"""Testing scaffold and runner command group."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from kaira.config import get_config
from kaira.console import console
from kaira.core.detector import write_with_check
from kaira.core.parser import camel_to_snake

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Testing scaffold and run commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("generate")
def test_generate(
    model_name: Annotated[Optional[str], typer.Argument(help="Name of the model to test.")] = None,
    generate_all: Annotated[bool, typer.Option("--all", help="Generate tests for all models.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Generate unit, integration, and security tests for a model."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    tests_dir = output_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "__init__.py").touch(exist_ok=True)

    env = _get_env()
    ctx = {"project_name": Path.cwd().name, "project_slug": Path.cwd().name.lower().replace("-", "_")}

    # Generate conftest.py if it doesn't exist
    conftest_path = tests_dir / "conftest.py"
    if not conftest_path.exists() or force:
        tmpl = env.get_template("test_conftest.py.j2")
        write_with_check(conftest_path, tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{conftest_path}[/cyan]")

    models_to_test = []
    if generate_all:
        models_to_test = [m.get("name") for m in config.generated_models]
    elif model_name:
        models_to_test = [model_name]
    else:
        console.print("[red]Error: Must specify either a model name or --all[/red]")
        raise typer.Exit(1)

    if not models_to_test:
        console.print("[yellow]No models found to generate tests for.[/yellow]")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Generating tests...", total=len(models_to_test) * 3)
        for name in models_to_test:
            model_entry = next((m for m in config.generated_models if m.get("name") == name), None)
            fields = model_entry.get("fields", []) if model_entry else []

            snake = camel_to_snake(name)
            ctx_model = {
                **ctx,
                "model_name": name,
                "snake_name": snake,
                "fields": fields,
                "models_dir": config.models_dir,
                "repositories_dir": config.repositories_dir,
                "schemas_dir": config.schemas_dir,
                "services_dir": config.services_dir,
                "routers_dir": config.routers_dir,
            }

            for t_type in ["router", "service", "repository"]:
                progress.update(task, description=f"[cyan]  {name}/{t_type}...")
                tmpl = env.get_template(f"test_{t_type}.py.j2")
                out_path = tests_dir / f"test_{snake}_{t_type}.py"
                write_with_check(out_path, tmpl.render(**ctx_model), force=force)
                console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")
                progress.advance(task)

    console.print(Panel(
        f"[green]Tests generated successfully for: {', '.join(models_to_test)}[/green]",
        title="Kaira — Test Scaffold",
        border_style="green",
    ))


@app.command("run")
def test_run() -> None:
    """Run pytest with coverage and display a Rich coverage report."""
    from kaira.config import get_venv_python
    python_exe = get_venv_python()
    console.print("[cyan]Running test suite with coverage...[/cyan]")
    cmd = [python_exe, "-m", "pytest", "tests/", "--cov=.", "--cov-report=term-missing"]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    
    # Print raw stderr if there are test failures or import errors
    if result.returncode != 0:
        console.print("[red]Tests failed or errored during run:[/red]")
        console.print(result.stderr or result.stdout)
        raise typer.Exit(result.returncode)

    # Parse pytest-cov console output to display a beautiful Rich table
    lines = result.stdout.split("\n")
    cov_lines = []
    start_parsing = False
    
    for line in lines:
        if "Name " in line and "Stmts " in line and "Miss " in line:
            start_parsing = True
            cov_lines.append(line)
            continue
        if start_parsing:
            if "---" in line:
                continue
            cov_lines.append(line)
            if "TOTAL" in line:
                break

    if cov_lines:
        table = Table(title="Kaira — Test Coverage Report", border_style="cyan")
        # Header
        headers = [h.strip() for h in cov_lines[0].split() if h.strip()]
        for header in headers:
            table.add_column(header, justify="left" if header == "Name" else "right")
            
        # Rows
        for line in cov_lines[1:]:
            parts = line.split()
            if len(parts) >= len(headers):
                # If path is long, show filename
                name = parts[0]
                row_data = [name] + parts[1:len(headers)]
                table.add_row(*row_data)
                
        console.print(table)
    else:
        # Fallback if no coverage table parsed
        console.print(result.stdout)
