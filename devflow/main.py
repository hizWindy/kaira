"""DevFlow CLI — Automated FastAPI Scaffolding Tool.

Entry point registered as: devflow = "devflow.main:app"
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich import print as rprint

from devflow import __version__
from devflow.console import console

# ── Import command apps ───────────────────────────────────────────────────────
from devflow.commands.generate import app as generate_app
from devflow.commands.relation import app as add_app
from devflow.commands.migrate import app as migrate_app
from devflow.commands.list_cmd import app as list_app
from devflow.commands.docs import app as docs_app
from devflow.commands.config_cmd import app as config_app
from devflow.commands.auth_cmd import app as auth_app
from devflow.commands.test_cmd import app as test_app
from devflow.commands.env_cmd import app as env_app
from devflow.commands.docker_cmd import app as docker_app
from devflow.commands.seed_cmd import app as seed_app
from devflow.commands.version_cmd import app as version_app
from devflow.commands.websocket_cmd import app as websocket_app
from devflow.commands.ci_cmd import app as ci_app
from devflow.commands.audit_cmd import app as audit_app
from devflow.commands.guide_cmd import app as guide_app

# ── Import standalone command functions ───────────────────────────────────────
from devflow.commands.project import init_command
from devflow.commands.info import info_command
from devflow.commands.check import check_command
from devflow.commands.diff import diff_command
from devflow.commands.health import health_command


# ── Root Typer app ────────────────────────────────────────────────────────────

app = typer.Typer(
    name="devflow",
    help=(
        "[bold cyan]DevFlow[/bold cyan] — Automated FastAPI scaffolding CLI.\n\n"
        "Generate complete 5-layer backend pipelines from model definitions.\n\n"
        "[dim]Version: " + __version__ + "[/dim]"
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
)

# ── Sub-command groups ────────────────────────────────────────────────────────

app.add_typer(generate_app, name="generate", help="Scaffold FastAPI backend layers.")
app.add_typer(add_app, name="add", help="Add relationships between models.")
app.add_typer(migrate_app, name="migrate", help="Alembic database migration commands.")
app.add_typer(list_app, name="list", help="List generated resources.")
app.add_typer(docs_app, name="docs", help="AI-powered API documentation generation.")
app.add_typer(config_app, name="config", help="Manage DevFlow project configuration.")
app.add_typer(auth_app, name="auth", help="Authentication scaffolding commands.")
app.add_typer(test_app, name="test", help="Testing scaffold and run commands.")
app.add_typer(env_app, name="env", help="Environment management commands.")
app.add_typer(docker_app, name="docker", help="Docker configuration scaffolding commands.")
app.add_typer(seed_app, name="seed", help="Database seeding commands.")
app.add_typer(version_app, name="version", help="API Versioning and deprecation commands.")
app.add_typer(websocket_app, name="websocket", help="WebSocket scaffolding commands.")
app.add_typer(ci_app, name="ci", help="CI/CD pipeline generation commands.")
app.add_typer(audit_app, name="audit", help="API auditing and security checking commands.")
app.add_typer(guide_app, name="guide", help="Interactive guides for all DevFlow operations.")


# ── Standalone commands ───────────────────────────────────────────────────────

@app.command("init")
def cmd_init(
    name: Annotated[
        Optional[str],
        typer.Argument(help="Name of the new project directory to create"),
    ] = None,
    db: Annotated[
        Optional[str],
        typer.Option("--db", help="Database type: postgresql, mysql, mongodb, sqlite"),
    ] = None,
    auth: Annotated[
        Optional[str],
        typer.Option("--auth", help="Auth type: jwt, oauth2, api-key, none"),
    ] = None,
    docker: Annotated[
        Optional[bool],
        typer.Option("--docker/--no-docker", help="Include Docker scaffolding config files"),
    ] = None,
    ci: Annotated[
        Optional[str],
        typer.Option("--ci", help="CI/CD platform: github, gitlab, bitbucket, none"),
    ] = None,
) -> None:
    """Scaffold a full FastAPI project structure in a named directory with interactive wizard config.

    Examples
    --------
    devflow init
    devflow init myproject
    devflow init myproject --db postgresql --auth jwt --docker
    """
    init_command(name=name, db=db, auth=auth, docker=docker, ci=ci)


@app.command("info")
def cmd_info() -> None:
    """Show current project config and all detected models."""
    info_command()


@app.command("check")
def cmd_check() -> None:
    """Run change detection — show what files would be overwritten."""
    check_command()


@app.command("diff")
def cmd_diff(
    model_name: Annotated[str, typer.Argument(help="PascalCase model name to diff")],
    fields: Annotated[
        Optional[str],
        typer.Option("--fields", "-f", help="Field definitions to regenerate with"),
    ] = None,
    layer: Annotated[
        Optional[str],
        typer.Option("--layer", "-l", help="Limit diff to a specific layer"),
    ] = None,
) -> None:
    """Show a diff between existing and newly generated files for MODEL_NAME.

    Examples
    --------
    devflow diff User
    devflow diff User --layer router
    devflow diff User --fields "username:str, email:str"
    """
    diff_command(model_name=model_name, fields=fields, layer=layer)


@app.command("health")
def cmd_health() -> None:
    """Run a comprehensive health audit of the DevFlow project."""
    health_command()


# ── Welcome banner (shown when --help is triggered at root level) ──────────────

def _version_callback(value: bool) -> None:
    if value:
        console.print(f"DevFlow v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True, help="Show version"),
    ] = None,
) -> None:
    """[bold cyan]DevFlow[/bold cyan] — Automated FastAPI scaffolding CLI.

    Generate complete 5-layer backend pipelines (model → repository → schema → service → router)
    from simple model definitions.

    [bold]Quick start:[/bold]

    \b
      devflow init
      devflow generate model User --fields "username:str, email:str, age:int"
      devflow generate model Post --fields "title:str, body:str" --tier full
      devflow migrate init
      devflow migrate make "initial migration"

    [bold]Docs:[/bold] https://github.com/your-org/devflow
    """


if __name__ == "__main__":
    app()
