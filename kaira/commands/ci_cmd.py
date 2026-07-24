"""CI/CD scaffolding command group."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from kaira.config import get_config
from kaira.console import console
from kaira.core.detector import write_with_check

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="CI/CD pipeline generation commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("generate")
def ci_generate(
    platform: Annotated[str, typer.Option("--platform", help="Platform: github, gitlab, bitbucket")] = "github",
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Generate pipeline config files with security analysis checks."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    env = _get_env()
    ctx = {"project_name": Path.cwd().name, "project_slug": Path.cwd().name.lower().replace("-", "_")}

    if platform == "github":
        gh_dir = output_root / ".github" / "workflows"
        gh_dir.mkdir(parents=True, exist_ok=True)
        
        # test.yml
        t_tmpl = env.get_template("ci_github.yml.j2")
        t_path = gh_dir / "test.yml"
        write_with_check(t_path, t_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{t_path}[/cyan]")

        # security.yml
        s_tmpl = env.get_template("ci_github_security.yml.j2")
        s_path = gh_dir / "security.yml"
        write_with_check(s_path, s_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{s_path}[/cyan]")

        # deploy.yml
        d_tmpl = env.get_template("ci_github_deploy.yml.j2")
        d_path = gh_dir / "deploy.yml"
        write_with_check(d_path, d_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{d_path}[/cyan]")

    elif platform == "gitlab":
        gl_tmpl = env.get_template("ci_gitlab.yml.j2")
        gl_path = output_root / ".gitlab-ci.yml"
        write_with_check(gl_path, gl_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{gl_path}[/cyan]")

    elif platform == "bitbucket":
        bb_tmpl = env.get_template("ci_bitbucket.yml.j2")
        bb_path = output_root / "bitbucket-pipelines.yml"
        write_with_check(bb_path, bb_tmpl.render(**ctx), force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{bb_path}[/cyan]")

    else:
        console.print(f"[red]Error: Unknown platform:[/red] {platform}")
        raise typer.Exit(1)

    console.print(Panel(
        f"[green]CI/CD ({platform}) pipeline generated successfully![/green]\n"
        "Includes automated tests, ruff, mypy, bandit, and pip-audit coverage checks.",
        title="Kaira — CI/CD Pipeline",
        border_style="green",
    ))
