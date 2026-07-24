"""Kaira menu command — interactive fuzzy-searchable command palette.

Presents all registered Kaira commands in a fuzzy-search prompt
so users can discover and run any command without memorising the full CLI.

After selection, the equivalent raw CLI command is printed before execution,
teaching users the full command syntax as they go.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Optional

import typer
from typing import Annotated

from devflow.console import console
from devflow.core.theme import Theme, sym

app = typer.Typer(
    help="Interactive fuzzy command palette — search and run any Kaira command.",
    invoke_without_command=True,
)

# ---------------------------------------------------------------------------
# Full command registry  (name → description → example invocation)
# ---------------------------------------------------------------------------

_COMMANDS: list[tuple[str, str, str]] = [
    # ── Scaffolding ──────────────────────────────────────────────────────────
    ("init", "Interactive wizard to scaffold a new project", "kaira init myproject"),
    (
        "generate model",
        "Generate complete 5-layer pipeline for a model",
        'kaira generate model User --fields "name:str, email:str"',
    ),
    (
        "generate router",
        "Generate only the FastAPI router for a model",
        "kaira generate router User",
    ),
    (
        "generate service",
        "Generate only the service layer for a model",
        "kaira generate service User",
    ),
    (
        "generate schema",
        "Generate only the Pydantic schemas for a model",
        "kaira generate schema User",
    ),
    (
        "generate repository",
        "Generate only the repository layer for a model",
        "kaira generate repository User",
    ),
    (
        "generate bulk",
        "Bulk-generate models from a JSON definition file",
        "kaira generate bulk models.json",
    ),
    (
        "add relation",
        "Add a relationship (one-to-many, many-to-one, etc.) to a model",
        "kaira add relation Post --has-many Comment",
    ),
    ("list models", "List all generated model files", "kaira list models"),
    (
        "list routes",
        "List all registered router endpoints with auth & rate limits",
        "kaira list routes",
    ),
    (
        "diff",
        "Show diff between existing and newly generated files",
        "kaira diff User",
    ),
    ("check", "Run change detection — show what would be overwritten", "kaira check"),
    ("info", "Display project config and detected models", "kaira info"),
    # ── Database ─────────────────────────────────────────────────────────────
    (
        "migrate init",
        "Initialize Alembic migrations in the project",
        "kaira migrate init",
    ),
    (
        "migrate make",
        "Create a new Alembic migration revision",
        'kaira migrate make "add users table"',
    ),
    (
        "migrate run",
        "Apply all pending migrations to the database",
        "kaira migrate run",
    ),
    (
        "migrate rollback",
        "Revert the last database migration",
        "kaira migrate rollback",
    ),
    (
        "db connect",
        "Interactive database setup and connection helper",
        "kaira db connect",
    ),
    ("db status", "Show database connection status and config", "kaira db status"),
    ("db reset", "Drop and recreate all database tables", "kaira db reset"),
    ("db shell", "Open an interactive SQL shell to the database", "kaira db shell"),
    ("db backup", "Backup the database to a file", "kaira db backup"),
    (
        "db restore",
        "Restore database from a backup file",
        "kaira db restore backup.sql",
    ),
    (
        "db switch",
        "Switch active database engine (e.g. postgresql, mysql, sqlite)",
        "kaira db switch postgresql",
    ),
    (
        "db benchmark",
        "Run database connection and query timing benchmark",
        "kaira db benchmark",
    ),
    # ── Cloud ────────────────────────────────────────────────────────────────
    (
        "cloud connect",
        "Connect to a cloud database provider (Supabase, Atlas, Firebase)",
        "kaira cloud connect",
    ),
    (
        "cloud status",
        "Show cloud provider, latency, and fallback state",
        "kaira cloud status",
    ),
    (
        "cloud test",
        "Run round-trip health check for the cloud connection",
        "kaira cloud test",
    ),
    (
        "cloud disconnect",
        "Revert cloud configuration and reset to SQLite",
        "kaira cloud disconnect",
    ),
    (
        "cloud fallback status",
        "Show local fallback mode, queue size, and conflict size",
        "kaira cloud fallback status",
    ),
    (
        "cloud fallback sync",
        "Attempt manual replay of local writes to cloud",
        "kaira cloud fallback sync",
    ),
    (
        "cloud fallback enable",
        "Generate fallback.py and enable cloud-local fallback",
        "kaira cloud fallback enable",
    ),
    (
        "cloud fallback disable",
        "Remove fallback.py and disable fallback wiring",
        "kaira cloud fallback disable",
    ),
    # ── Security & Auth ───────────────────────────────────────────────────────
    (
        "auth generate",
        "Scaffold JWT / OAuth2 / API-key authentication layer",
        "kaira auth generate --type jwt",
    ),
    (
        "auth add-guard",
        "Secure an existing router with authentication dependency",
        "kaira auth add-guard users",
    ),
    (
        "audit routes",
        "List all project endpoints and their handlers",
        "kaira audit routes",
    ),
    (
        "audit security",
        "Check routes, schemas, models, and envs for security issues",
        "kaira audit security",
    ),
    (
        "audit unused",
        "Find unused/unregistered generated router files",
        "kaira audit unused",
    ),
    # ── Environment ───────────────────────────────────────────────────────────
    (
        "env init",
        "Initialize environment (.env) files and config schema",
        "kaira env init",
    ),
    (
        "env add",
        "Add or update environment variables across profiles",
        "kaira env add DATABASE_URL value",
    ),
    (
        "env switch",
        "Switch the active active environment profile",
        "kaira env switch production",
    ),
    (
        "env validate",
        "Validate environment keys against security and schema rules",
        "kaira env validate",
    ),
    # ── Docker & CI ───────────────────────────────────────────────────────────
    (
        "docker init",
        "Generate Dockerfile and docker-compose configurations",
        "kaira docker init --with-compose",
    ),
    (
        "docker build",
        "Build the application Docker image",
        "kaira docker build --tag myapp",
    ),
    (
        "docker run",
        "Run the application Docker container locally",
        "kaira docker run --tag myapp",
    ),
    (
        "ci generate",
        "Generate CI/CD pipeline configuration (GitHub, GitLab, etc.)",
        "kaira ci generate --platform github",
    ),
    # ── Quality ───────────────────────────────────────────────────────────────
    (
        "quality lint",
        "Run ruff linter checks on project files",
        "kaira quality lint .",
    ),
    (
        "quality typecheck",
        "Run mypy static type analysis on project files",
        "kaira quality typecheck .",
    ),
    (
        "quality format",
        "Auto-format python code using ruff formatter",
        "kaira quality format .",
    ),
    (
        "quality scan",
        "Scan project files for security bugs using bandit",
        "kaira quality scan .",
    ),
    (
        "quality quality",
        "Run all linter, typecheck, format, and scanning checks",
        "kaira quality quality .",
    ),
    # ── Testing ───────────────────────────────────────────────────────────────
    (
        "test generate",
        "Generate complete pytest test suite scaffolding",
        "kaira test generate --all",
    ),
    ("test run", "Run project test suite with pytest", "kaira test run"),
    # ── Deployment ────────────────────────────────────────────────────────────
    (
        "deploy generate",
        "Generate hosting platform configuration files",
        "kaira deploy generate --platform railway",
    ),
    (
        "deploy checklist",
        "Verify project deployment readiness checklist",
        "kaira deploy checklist",
    ),
    (
        "deploy check",
        "Run checklist and exit 1 if any items fail",
        "kaira deploy check",
    ),
    (
        "deploy run",
        "Trigger application deployment to the platform",
        "kaira deploy run --platform railway",
    ),
    # ── Dependency Management ─────────────────────────────────────────────────
    ("deps check", "Check for outdated packages and updates", "kaira deps check"),
    (
        "deps update",
        "Update and pin dependencies to secure versions",
        "kaira deps update",
    ),
    (
        "deps audit",
        "Audit dependencies for known security vulnerabilities",
        "kaira deps audit",
    ),
    ("deps tree", "Print visual dependency installation tree", "kaira deps tree"),
    (
        "deps add",
        "Add a new package dependency and pin in configuration",
        "kaira deps add fastapi-limiter",
    ),
    (
        "deps remove",
        "Remove a dependency package from project",
        "kaira deps remove some-package",
    ),
    # ── Caching ───────────────────────────────────────────────────────────────
    ("cache init", "Initialize Redis cache connection config", "kaira cache init"),
    (
        "cache status",
        "Show Redis connection and configuration status",
        "kaira cache status",
    ),
    (
        "cache add",
        "Add caching decorator to a GET endpoint route",
        "kaira cache add GET /users --ttl 300",
    ),
    (
        "cache clear",
        "Flush cached entries from Redis (route or entire cache)",
        "kaira cache clear --all",
    ),
    # ── Background Tasks ──────────────────────────────────────────────────────
    (
        "task init",
        "Initialize Celery background task worker support",
        "kaira task init",
    ),
    (
        "task generate",
        "Generate a new background task or scheduled task",
        "kaira task generate send_email",
    ),
    (
        "task list",
        "List all registered background tasks in the project",
        "kaira task list",
    ),
    (
        "task run",
        "Trigger and execute a background task immediately",
        "kaira task run send_email",
    ),
    (
        "task monitor",
        "Launch Flower dashboard to monitor Celery workers",
        "kaira task monitor",
    ),
    # ── API & Profiling ───────────────────────────────────────────────────────
    (
        "api export",
        "Export OpenAPI schema specification to JSON or YAML",
        "kaira api export --format json",
    ),
    (
        "api validate",
        "Validate OpenAPI spec schema for correctness",
        "kaira api validate",
    ),
    ("api list", "Show all routes from the OpenAPI schema", "kaira api list"),
    (
        "api test",
        "Perform interactive API client request testing",
        "kaira api test GET /users",
    ),
    (
        "api postman",
        "Export project routes into a Postman collection JSON",
        "kaira api postman",
    ),
    (
        "api client",
        "Generate typed client SDK from OpenAPI schema",
        "kaira api client --lang typescript",
    ),
    (
        "profile run",
        "Profile latency and response statistics on a route",
        "kaira profile run GET /users",
    ),
    (
        "profile report",
        "Display results from the last run profile report",
        "kaira profile report",
    ),
    ("loadtest run", "Run locust load testing on endpoints", "kaira loadtest run"),
    # ── Integrations & Middleware ─────────────────────────────────────────────
    (
        "integrate add",
        "Add a third-party service integration",
        "kaira integrate add email/sendgrid",
    ),
    (
        "integrate list",
        "List all supported third-party integrations",
        "kaira integrate list",
    ),
    (
        "middleware add",
        "Scaffold custom middleware logic handler",
        "kaira middleware add logging",
    ),
    (
        "middleware list",
        "List registered middlewares in the system",
        "kaira middleware list",
    ),
    (
        "middleware remove",
        "De-register and remove a custom middleware",
        "kaira middleware remove logging",
    ),
    (
        "event generate",
        "Scaffold FastAPI startup/shutdown event handlers",
        "kaira event generate",
    ),
    (
        "notify init",
        "Initialize email, SMS, or push notification services",
        "kaira notify init --type email",
    ),
    (
        "notify generate",
        "Generate a new notification template",
        "kaira notify generate welcome_email",
    ),
    (
        "notify test",
        "Send a test notification to verify delivery",
        "kaira notify test welcome_email",
    ),
    ("notify list", "List all configured notification channels", "kaira notify list"),
    (
        "flags init",
        "Initialize feature flags with fail-closed configuration",
        "kaira flags init",
    ),
    (
        "flags add",
        "Add a new feature flag to the flags module",
        "kaira flags add dark_mode",
    ),
    (
        "flags enable",
        "Enable a feature flag in the system",
        "kaira flags enable dark_mode",
    ),
    (
        "flags disable",
        "Disable a feature flag in the system",
        "kaira flags disable dark_mode",
    ),
    ("flags list", "List status of all registered feature flags", "kaira flags list"),
    # ── Health & Monitoring ───────────────────────────────────────────────────
    ("health", "Run a comprehensive local system health check", "kaira health"),
    (
        "health-endpoint generate",
        "Generate secure /health status endpoint",
        "kaira health-endpoint generate",
    ),
    (
        "status",
        "View project status, model count, and configuration recap",
        "kaira status",
    ),
    (
        "recap show",
        "Show recap summary of recently executed commands",
        "kaira recap show",
    ),
    # ── Docs & Versioning ─────────────────────────────────────────────────────
    (
        "docs generate",
        "Generate automated Markdown API documentation",
        "kaira docs generate",
    ),
    (
        "version create",
        "Create a new API version prefix group",
        "kaira version create v2",
    ),
    (
        "version migrate",
        "Migrate models to a new API version target",
        "kaira version migrate v2",
    ),
    ("version list", "List all configured API versions", "kaira version list"),
    # ── Seeding ───────────────────────────────────────────────────────────────
    (
        "seed generate",
        "Generate random seed database populate data",
        "kaira seed generate User",
    ),
    (
        "seed run",
        "Populate the database using the seed generator script",
        "kaira seed run",
    ),
    (
        "seed clear",
        "Clear all data created by seeders (destructive)",
        "kaira seed clear",
    ),
    # ── Server ────────────────────────────────────────────────────────────────
    ("run", "Start the FastAPI development or production server", "kaira run"),
    # ── WebSocket ─────────────────────────────────────────────────────────────
    (
        "websocket generate",
        "Scaffold async WebSocket manager and router",
        "kaira websocket generate",
    ),
    # ── Guides ────────────────────────────────────────────────────────────────
    ("guide", "Browse all available Kaira tutorial guides", "kaira guide"),
]


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def menu_main(
    ctx: typer.Context,
    query: Annotated[
        Optional[str],
        typer.Argument(help="Optional pre-filter search query"),
    ] = None,
) -> None:
    """Open an interactive fuzzy-searchable menu of all Kaira commands.

    Selecting a command prints the equivalent raw CLI invocation before running
    it — teaching users the full syntax as they go.

    Examples
    --------
    kaira menu
    kaira menu mig
    """
    if ctx.invoked_subcommand is not None:
        return

    from devflow.core import prompts
    from rich.panel import Panel
    from rich.table import Table
    from rich.align import Align
    from rich.text import Text

    # Build fuzzy choices: "command name  —  description"
    choices = [
        (cmd, f"{desc}  [{Theme.MUTED}]e.g. {example}[/{Theme.MUTED}]")
        for cmd, desc, example in _COMMANDS
    ]
    # Add a dedicated Quit option for user convenience
    choices.append(
        (
            "[Quit]",
            f"Exit the command palette  [{Theme.MUTED}]or press Esc/Ctrl+C[/{Theme.MUTED}]",
        )
    )

    # Render a beautiful header Panel detailing palette information and shortcuts
    shortcuts = Table.grid(padding=(0, 2))
    shortcuts.add_row("[bold cyan]Type[/bold cyan]", "to filter in real-time")
    shortcuts.add_row("[bold cyan]↑ / ↓[/bold cyan]", "to navigate options")
    shortcuts.add_row("[bold cyan]Enter[/bold cyan]", "to execute command")
    shortcuts.add_row("[bold cyan]Esc / Ctrl+C[/bold cyan]", "to cancel and exit")

    welcome_text = Text.assemble(
        (f"{sym('BOLT')} ", f"bold {Theme.PRIMARY}"),
        ("Kaira Command Palette", "bold white"),
        ("\nSearch and run any Kaira CLI command instantly.\n\n", Theme.MUTED),
    )

    from rich.console import Group

    console.print()
    console.print(
        Panel(
            Group(
                Align.center(welcome_text),
                Align.center(shortcuts),
            ),
            title="[bold cyan]Interactive Search[/bold cyan]",
            border_style=Theme.PRIMARY,
            padding=(1, 2),
        )
    )
    console.print()

    selected = prompts.fuzzy_select(
        "Search commands:",
        choices=choices,
        default=query or "",
        flag="--query",
    )

    if selected == "[Quit]":
        console.print(f"[{Theme.MUTED}]Cancelled.[/{Theme.MUTED}]")
        raise typer.Exit(0)

    # Find the example invocation for the selected command
    example_cmd = next(
        (ex for cmd, _desc, ex in _COMMANDS if cmd == selected),
        f"kaira {selected}",
    )

    console.print(
        f"\n[{Theme.MUTED}]Running:[/{Theme.MUTED}] [{Theme.PRIMARY}]{example_cmd}[/{Theme.PRIMARY}]\n"
    )

    # Execute the example command by splitting and running as a subprocess
    parts = example_cmd.split()
    # Replace the "kaira" command token with the actual executable path for reliability
    parts[0] = sys.executable
    parts.insert(1, "-m")
    parts.insert(2, "devflow.main")

    # Actually launch kaira <subcommand> — propagate exit code
    result = subprocess.run([sys.executable, "-m", "devflow.main"] + parts[3:])
    raise typer.Exit(result.returncode)
