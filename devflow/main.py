"""DevFlow CLI — Automated FastAPI Scaffolding Tool.

Entry point registered as: devflow = "devflow.main:app"
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer

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

# ── Phase 4 command apps ──────────────────────────────────────────────────────
from devflow.commands.status_cmd import app as status_app
from devflow.commands.recap_cmd import app as recap_app
from devflow.commands.db_cmd import app as db_app
from devflow.commands.deps_cmd import app as deps_app
from devflow.commands.quality_cmd import app as quality_app
from devflow.commands.cache_cmd import app as cache_app
from devflow.commands.task_cmd import app as task_app
from devflow.commands.integrate_cmd import app as integrate_app
from devflow.commands.api_cmd import app as api_cmd_app
from devflow.commands.profile_cmd import app as profile_app
from devflow.commands.loadtest_cmd import app as loadtest_app
from devflow.commands.deploy_cmd import app as deploy_app
from devflow.commands.middleware_cmd import app as middleware_app
from devflow.commands.event_cmd import app as event_app
from devflow.commands.notify_cmd import app as notify_app
from devflow.commands.flags_cmd import app as flags_app
from devflow.commands.health_endpoint_cmd import app as health_endpoint_app
from devflow.commands.run_cmd import app as run_app

# ── Phase 5 command apps ──────────────────────────────────────────────────────
from devflow.commands.menu_cmd import app as menu_app
from devflow.commands.cloud_cmd import app as cloud_app  # noqa: F401 — registered below

# ── Phase 5.5 command apps ────────────────────────────────────────────────────
from devflow.commands.sync_cmd import app as sync_app

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

# ── Sub-command groups — Phase 1–3 ────────────────────────────────────────────

app.add_typer(generate_app, name="generate", help="Scaffold FastAPI backend layers.")
app.add_typer(add_app, name="add", help="Add relationships between models.")
app.add_typer(migrate_app, name="migrate", help="Alembic database migration commands.")
app.add_typer(list_app, name="list", help="List generated resources.")
app.add_typer(docs_app, name="docs", help="AI-powered API documentation generation.")
app.add_typer(config_app, name="config", help="Manage DevFlow project configuration.")
app.add_typer(auth_app, name="auth", help="Authentication scaffolding commands.")
app.add_typer(test_app, name="test", help="Testing scaffold and run commands.")
app.add_typer(env_app, name="env", help="Environment management commands.")
app.add_typer(
    docker_app, name="docker", help="Docker configuration scaffolding commands."
)
app.add_typer(seed_app, name="seed", help="Database seeding commands.")
app.add_typer(
    version_app, name="version", help="API Versioning and deprecation commands."
)
app.add_typer(websocket_app, name="websocket", help="WebSocket scaffolding commands.")
app.add_typer(ci_app, name="ci", help="CI/CD pipeline generation commands.")
app.add_typer(
    audit_app, name="audit", help="API auditing and security checking commands."
)
app.add_typer(
    guide_app, name="guide", help="Interactive guides for all DevFlow operations."
)

# ── Sub-command groups — Phase 4 ──────────────────────────────────────────────

app.add_typer(status_app, name="status", help="Live project status snapshot.")
app.add_typer(recap_app, name="recap", help="Command history viewer.")
app.add_typer(db_app, name="db", help="Database connection, status, and management.")
app.add_typer(
    deps_app,
    name="deps",
    help="Dependency management — check, update, audit, tree, add, remove.",
)
app.add_typer(
    quality_app,
    name="quality",
    help="Code quality tools — lint, typecheck, format, scan, audit.",
)
app.add_typer(cache_app, name="cache", help="Redis cache management and route caching.")
app.add_typer(task_app, name="task", help="Celery background task scaffolding.")
app.add_typer(integrate_app, name="integrate", help="Third-party service integrations.")
app.add_typer(
    api_cmd_app, name="api", help="API inspection, testing, and client generation."
)
app.add_typer(
    profile_app, name="profile", help="Route profiling and latency measurement."
)
app.add_typer(
    loadtest_app, name="loadtest", help="Load testing for local FastAPI routes."
)
app.add_typer(
    deploy_app, name="deploy", help="Deployment config generation and checklist."
)
app.add_typer(
    middleware_app, name="middleware", help="Middleware scaffolding and management."
)
app.add_typer(event_app, name="event", help="FastAPI lifespan event scaffolding.")
app.add_typer(notify_app, name="notify", help="Notification service scaffolding.")
app.add_typer(flags_app, name="flags", help="Feature flag management.")
app.add_typer(
    health_endpoint_app,
    name="health-endpoint",
    help="Generate a /health monitoring endpoint.",
)
app.add_typer(
    run_app,
    name="run",
    help="Start the FastAPI dev/prod server (wraps fastapi dev / fastapi run).",
)

# ── Sub-command groups — Phase 5 ──────────────────────────────────────────────

app.add_typer(
    menu_app,
    name="menu",
    help="☁️  Interactive fuzzy command palette — search and run any DevFlow command.",
)
app.add_typer(
    cloud_app,
    name="cloud",
    help="☁️  Cloud database providers (Supabase, Atlas, Firebase) and fallback.",
)

# ── Sub-command groups — Phase 5.5 ────────────────────────────────────────────

app.add_typer(
    sync_app, name="sync", help="Cascade model field changes across all 5 layers."
)


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
        typer.Option(
            "--docker/--no-docker", help="Include Docker scaffolding config files"
        ),
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
        from devflow.core.theme import Theme, attribution

        console.print(f"DevFlow v{__version__}")
        console.print(f"[{Theme.MUTED}]{attribution()}[/{Theme.MUTED}]")
        raise typer.Exit()


@app.command("about")
def cmd_about() -> None:
    """Show DevFlow version, tagline, and attribution."""
    from rich.panel import Panel

    from devflow.core.theme import Theme, attribution, sym

    bolt = sym("BOLT")
    from devflow.core.theme import PROJECT_URL

    body = (
        f"[{Theme.PRIMARY}]DevFlow[/{Theme.PRIMARY}]  v{__version__}\n"
        f"[{Theme.MUTED}]Continuous model-level FastAPI scaffolding[/{Theme.MUTED}]\n\n"
        f"{attribution()}\n"
        f"[{Theme.MUTED}]{PROJECT_URL}[/{Theme.MUTED}]"
    )
    console.print(
        Panel(
            body,
            title=f"[{Theme.PRIMARY}]{bolt} DevFlow[/{Theme.PRIMARY}]",
            border_style=Theme.BORDER_PRIMARY,
            expand=False,
        )
    )


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show version",
        ),
    ] = None,
    quiet: Annotated[
        Optional[bool],
        typer.Option(
            "--quiet", "-q", help="Suppress next-steps hints and informational panels"
        ),
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

    [bold]Phase 5 — Cloud:[/bold]

    \b
      devflow cloud connect        Connect to Supabase / MongoDB Atlas / Firebase
      devflow cloud status         Cloud connection and fallback status
      devflow menu                 Interactive command palette (fuzzy search)
    """
    # Phase 5: first-run onboarding (TTY + no args only, never in CI)
    try:
        from devflow.commands.onboarding import run_onboarding

        run_onboarding()
    except Exception:  # never crash the main CLI due to onboarding
        pass


if __name__ == "__main__":
    app()
