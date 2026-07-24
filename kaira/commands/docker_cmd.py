"""Docker configuration scaffold and runner command group."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from devflow.config import get_config
from devflow.console import console
from devflow.core.detector import write_with_check

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Docker scaffolding and execution commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("init")
def docker_init(
    with_compose: Annotated[bool, typer.Option("--with-compose", help="Scaffold docker-compose files.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Scaffold Dockerfile, .dockerignore, and docker-compose files with security hardening."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    env = _get_env()
    ctx = {"project_name": Path.cwd().name, "project_slug": Path.cwd().name.lower().replace("-", "_")}

    # Dockerfile
    df_tmpl = env.get_template("docker_dockerfile.j2")
    df_path = output_root / "Dockerfile"
    write_with_check(df_path, df_tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{df_path}[/cyan]")

    # .dockerignore
    di_tmpl = env.get_template("docker_ignore.j2")
    di_path = output_root / ".dockerignore"
    write_with_check(di_path, di_tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{di_path}[/cyan]")

    # Optional Docker Compose files
    if with_compose:
        # docker-compose.yml
        dc_tmpl = env.get_template("docker_compose.j2")
        dc_path = output_root / "docker-compose.yml"
        write_with_check(dc_path, dc_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{dc_path}[/cyan]")

        # docker-compose.prod.yml
        dcp_tmpl = env.get_template("docker_compose_prod.j2")
        dcp_path = output_root / "docker-compose.prod.yml"
        write_with_check(dcp_path, dcp_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{dcp_path}[/cyan]")

    console.print(Panel(
        f"[green]Docker environment initialized successfully![/green]",
        title="Kaira — Docker Scaffold",
        border_style="green",
    ))


@app.command("build")
def docker_build(
    tag: Annotated[str, typer.Option("-t", "--tag", help="Build tag name.")] = "devflow-app",
) -> None:
    """Build the docker container image."""
    console.print(f"[cyan]Building Docker image [bold]{tag}[/bold]...[/cyan]")
    cmd = ["docker", "build", "-t", tag, "."]
    try:
        subprocess.run(cmd, check=True)
        console.print(f"[green]✔ Image {tag} built successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error: Docker build failed: {e}[/red]")
        raise typer.Exit(1)


@app.command("run")
def docker_run(
    tag: Annotated[str, typer.Option("-t", "--tag", help="Tag name of the image to run.")] = "devflow-app",
    port: Annotated[int, typer.Option("-p", "--port", help="Port mapping.")] = 8000,
) -> None:
    """Run the secure docker container instance."""
    console.print(f"[cyan]Running Docker image [bold]{tag}[/bold] on port {port}...[/cyan]")
    cmd = [
        "docker", "run", "-d",
        "-p", f"{port}:8000",
        "--read-only",
        "--security-opt", "no-new-privileges:true",
        "--env-file", ".env",
        tag
    ]
    try:
        subprocess.run(cmd, check=True)
        console.print(f"[green]✔ Container running successfully. Access at http://localhost:{port}[/green]")
    except Exception as e:
        console.print(f"[red]Error: Failed to run Docker container: {e}[/red]")
        raise typer.Exit(1)
