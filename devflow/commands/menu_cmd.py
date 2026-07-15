"""DevFlow menu command — interactive fuzzy-searchable command palette.

Presents all registered DevFlow commands in a fuzzy-search prompt
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
    help="Interactive fuzzy command palette — search and run any DevFlow command.",
    invoke_without_command=True,
)

# ---------------------------------------------------------------------------
# Full command registry  (name → description → example invocation)
# ---------------------------------------------------------------------------

_COMMANDS: list[tuple[str, str, str]] = [
    # ── Scaffolding ──────────────────────────────────────────────────────────
    ("init", "Interactive wizard to scaffold a new project", "devflow init myproject"),
    (
        "generate model",
        "Generate complete 5-layer pipeline for a model",
        'devflow generate model User --fields "name:str, email:str"',
    ),
    (
        "generate router",
        "Generate only the FastAPI router for a model",
        "devflow generate router User",
    ),
    (
        "generate service",
        "Generate only the service layer for a model",
        "devflow generate service User",
    ),
    (
        "generate schema",
        "Generate only the Pydantic schemas for a model",
        "devflow generate schema User",
    ),
    (
        "generate repository",
        "Generate only the repository layer for a model",
        "devflow generate repository User",
    ),
    (
        "generate bulk",
        "Bulk-generate models from a JSON definition file",
        "devflow generate bulk models.json",
    ),
    (
        "add relation",
        "Add a relationship (one-to-many, many-to-one, etc.) to a model",
        "devflow add relation Post --has-many Comment",
    ),
    ("list models", "List all generated model files", "devflow list models"),
    (
        "list routes",
        "List all registered router endpoints with auth & rate limits",
        "devflow list routes",
    ),
    (
        "diff",
        "Show diff between existing and newly generated files",
        "devflow diff User",
    ),
    ("check", "Run change detection — show what would be overwritten", "devflow check"),
    ("info", "Display project config and detected models", "devflow info"),
    # ── Database ─────────────────────────────────────────────────────────────
    (
        "migrate init",
        "Initialize Alembic migrations in the project",
        "devflow migrate init",
    ),
    (
        "migrate make",
        "Create a new Alembic migration revision",
        'devflow migrate make "add users table"',
    ),
    (
        "migrate run",
        "Apply all pending migrations to the database",
        "devflow migrate run",
    ),
    (
        "migrate rollback",
        "Revert the last database migration",
        "devflow migrate rollback",
    ),
    (
        "db connect",
        "Interactive database setup and connection helper",
        "devflow db connect",
    ),
    ("db status", "Show database connection status and config", "devflow db status"),
    ("db reset", "Drop and recreate all database tables", "devflow db reset"),
    ("db shell", "Open an interactive SQL shell to the database", "devflow db shell"),
    ("db backup", "Backup the database to a file", "devflow db backup"),
    (
        "db restore",
        "Restore database from a backup file",
        "devflow db restore backup.sql",
    ),
    (
        "db switch",
        "Switch active database engine (e.g. postgresql, mysql, sqlite)",
        "devflow db switch postgresql",
    ),
    (
        "db benchmark",
        "Run database connection and query timing benchmark",
        "devflow db benchmark",
    ),
    # ── Cloud ────────────────────────────────────────────────────────────────
    (
        "cloud connect",
        "Connect to a cloud database provider (Supabase, Atlas, Firebase)",
        "devflow cloud connect",
    ),
    (
        "cloud status",
        "Show cloud provider, latency, and fallback state",
        "devflow cloud status",
    ),
    (
        "cloud test",
        "Run round-trip health check for the cloud connection",
        "devflow cloud test",
    ),
    (
        "cloud disconnect",
        "Revert cloud configuration and reset to SQLite",
        "devflow cloud disconnect",
    ),
    (
        "cloud fallback status",
        "Show local fallback mode, queue size, and conflict size",
        "devflow cloud fallback status",
    ),
    (
        "cloud fallback sync",
        "Attempt manual replay of local writes to cloud",
        "devflow cloud fallback sync",
    ),
    (
        "cloud fallback enable",
        "Generate fallback.py and enable cloud-local fallback",
        "devflow cloud fallback enable",
    ),
    (
        "cloud fallback disable",
        "Remove fallback.py and disable fallback wiring",
        "devflow cloud fallback disable",
    ),
    # ── Security & Auth ───────────────────────────────────────────────────────
    (
        "auth generate",
        "Scaffold JWT / OAuth2 / API-key authentication layer",
        "devflow auth generate --type jwt",
    ),
    (
        "auth add-guard",
        "Secure an existing router with authentication dependency",
        "devflow auth add-guard users",
    ),
    (
        "audit routes",
        "List all project endpoints and their handlers",
        "devflow audit routes",
    ),
    (
        "audit security",
        "Check routes, schemas, models, and envs for security issues",
        "devflow audit security",
    ),
    (
        "audit unused",
        "Find unused/unregistered generated router files",
        "devflow audit unused",
    ),
    # ── Environment ───────────────────────────────────────────────────────────
    (
        "env init",
        "Initialize environment (.env) files and config schema",
        "devflow env init",
    ),
    (
        "env add",
        "Add or update environment variables across profiles",
        "devflow env add DATABASE_URL value",
    ),
    (
        "env switch",
        "Switch the active active environment profile",
        "devflow env switch production",
    ),
    (
        "env validate",
        "Validate environment keys against security and schema rules",
        "devflow env validate",
    ),
    # ── Docker & CI ───────────────────────────────────────────────────────────
    (
        "docker init",
        "Generate Dockerfile and docker-compose configurations",
        "devflow docker init --with-compose",
    ),
    (
        "docker build",
        "Build the application Docker image",
        "devflow docker build --tag myapp",
    ),
    (
        "docker run",
        "Run the application Docker container locally",
        "devflow docker run --tag myapp",
    ),
    (
        "ci generate",
        "Generate CI/CD pipeline configuration (GitHub, GitLab, etc.)",
        "devflow ci generate --platform github",
    ),
    # ── Quality ───────────────────────────────────────────────────────────────
    (
        "quality lint",
        "Run ruff linter checks on project files",
        "devflow quality lint .",
    ),
    (
        "quality typecheck",
        "Run mypy static type analysis on project files",
        "devflow quality typecheck .",
    ),
    (
        "quality format",
        "Auto-format python code using ruff formatter",
        "devflow quality format .",
    ),
    (
        "quality scan",
        "Scan project files for security bugs using bandit",
        "devflow quality scan .",
    ),
    (
        "quality quality",
        "Run all linter, typecheck, format, and scanning checks",
        "devflow quality quality .",
    ),
    # ── Testing ───────────────────────────────────────────────────────────────
    (
        "test generate",
        "Generate complete pytest test suite scaffolding",
        "devflow test generate --all",
    ),
    ("test run", "Run project test suite with pytest", "devflow test run"),
    # ── Deployment ────────────────────────────────────────────────────────────
    (
        "deploy generate",
        "Generate hosting platform configuration files",
        "devflow deploy generate --platform railway",
    ),
    (
        "deploy checklist",
        "Verify project deployment readiness checklist",
        "devflow deploy checklist",
    ),
    (
        "deploy check",
        "Run checklist and exit 1 if any items fail",
        "devflow deploy check",
    ),
    (
        "deploy run",
        "Trigger application deployment to the platform",
        "devflow deploy run --platform railway",
    ),
    # ── Dependency Management ─────────────────────────────────────────────────
    ("deps check", "Check for outdated packages and updates", "devflow deps check"),
    (
        "deps update",
        "Update and pin dependencies to secure versions",
        "devflow deps update",
    ),
    (
        "deps audit",
        "Audit dependencies for known security vulnerabilities",
        "devflow deps audit",
    ),
    ("deps tree", "Print visual dependency installation tree", "devflow deps tree"),
    (
        "deps add",
        "Add a new package dependency and pin in configuration",
        "devflow deps add fastapi-limiter",
    ),
    (
        "deps remove",
        "Remove a dependency package from project",
        "devflow deps remove some-package",
    ),
    # ── Caching ───────────────────────────────────────────────────────────────
    ("cache init", "Initialize Redis cache connection config", "devflow cache init"),
    (
        "cache status",
        "Show Redis connection and configuration status",
        "devflow cache status",
    ),
    (
        "cache add",
        "Add caching decorator to a GET endpoint route",
        "devflow cache add GET /users --ttl 300",
    ),
    (
        "cache clear",
        "Flush cached entries from Redis (route or entire cache)",
        "devflow cache clear --all",
    ),
    # ── Background Tasks ──────────────────────────────────────────────────────
    (
        "task init",
        "Initialize Celery background task worker support",
        "devflow task init",
    ),
    (
        "task generate",
        "Generate a new background task or scheduled task",
        "devflow task generate send_email",
    ),
    (
        "task list",
        "List all registered background tasks in the project",
        "devflow task list",
    ),
    (
        "task run",
        "Trigger and execute a background task immediately",
        "devflow task run send_email",
    ),
    (
        "task monitor",
        "Launch Flower dashboard to monitor Celery workers",
        "devflow task monitor",
    ),
    # ── API & Profiling ───────────────────────────────────────────────────────
    (
        "api export",
        "Export OpenAPI schema specification to JSON or YAML",
        "devflow api export --format json",
    ),
    (
        "api validate",
        "Validate OpenAPI spec schema for correctness",
        "devflow api validate",
    ),
    ("api list", "Show all routes from the OpenAPI schema", "devflow api list"),
    (
        "api test",
        "Perform interactive API client request testing",
        "devflow api test GET /users",
    ),
    (
        "api postman",
        "Export project routes into a Postman collection JSON",
        "devflow api postman",
    ),
    (
        "api client",
        "Generate typed client SDK from OpenAPI schema",
        "devflow api client --lang typescript",
    ),
    (
        "profile run",
        "Profile latency and response statistics on a route",
        "devflow profile run GET /users",
    ),
    (
        "profile report",
        "Display results from the last run profile report",
        "devflow profile report",
    ),
    ("loadtest run", "Run locust load testing on endpoints", "devflow loadtest run"),
    # ── Integrations & Middleware ─────────────────────────────────────────────
    (
        "integrate add",
        "Add a third-party service integration",
        "devflow integrate add email/sendgrid",
    ),
    (
        "integrate list",
        "List all supported third-party integrations",
        "devflow integrate list",
    ),
    (
        "middleware add",
        "Scaffold custom middleware logic handler",
        "devflow middleware add logging",
    ),
    (
        "middleware list",
        "List registered middlewares in the system",
        "devflow middleware list",
    ),
    (
        "middleware remove",
        "De-register and remove a custom middleware",
        "devflow middleware remove logging",
    ),
    (
        "event generate",
        "Scaffold FastAPI startup/shutdown event handlers",
        "devflow event generate",
    ),
    (
        "notify init",
        "Initialize email, SMS, or push notification services",
        "devflow notify init --type email",
    ),
    (
        "notify generate",
        "Generate a new notification template",
        "devflow notify generate welcome_email",
    ),
    (
        "notify test",
        "Send a test notification to verify delivery",
        "devflow notify test welcome_email",
    ),
    ("notify list", "List all configured notification channels", "devflow notify list"),
    (
        "flags init",
        "Initialize feature flags with fail-closed configuration",
        "devflow flags init",
    ),
    (
        "flags add",
        "Add a new feature flag to the flags module",
        "devflow flags add dark_mode",
    ),
    (
        "flags enable",
        "Enable a feature flag in the system",
        "devflow flags enable dark_mode",
    ),
    (
        "flags disable",
        "Disable a feature flag in the system",
        "devflow flags disable dark_mode",
    ),
    ("flags list", "List status of all registered feature flags", "devflow flags list"),
    # ── Health & Monitoring ───────────────────────────────────────────────────
    ("health", "Run a comprehensive local system health check", "devflow health"),
    (
        "health-endpoint generate",
        "Generate secure /health status endpoint",
        "devflow health-endpoint generate",
    ),
    (
        "status",
        "View project status, model count, and configuration recap",
        "devflow status",
    ),
    (
        "recap show",
        "Show recap summary of recently executed commands",
        "devflow recap show",
    ),
    # ── Docs & Versioning ─────────────────────────────────────────────────────
    (
        "docs generate",
        "Generate automated Markdown API documentation",
        "devflow docs generate",
    ),
    (
        "version create",
        "Create a new API version prefix group",
        "devflow version create v2",
    ),
    (
        "version migrate",
        "Migrate models to a new API version target",
        "devflow version migrate v2",
    ),
    ("version list", "List all configured API versions", "devflow version list"),
    # ── Seeding ───────────────────────────────────────────────────────────────
    (
        "seed generate",
        "Generate random seed database populate data",
        "devflow seed generate User",
    ),
    (
        "seed run",
        "Populate the database using the seed generator script",
        "devflow seed run",
    ),
    (
        "seed clear",
        "Clear all data created by seeders (destructive)",
        "devflow seed clear",
    ),
    # ── Server ────────────────────────────────────────────────────────────────
    ("run", "Start the FastAPI development or production server", "devflow run"),
    # ── WebSocket ─────────────────────────────────────────────────────────────
    (
        "websocket generate",
        "Scaffold async WebSocket manager and router",
        "devflow websocket generate",
    ),
    # ── Guides ────────────────────────────────────────────────────────────────
    ("guide", "Browse all available DevFlow tutorial guides", "devflow guide"),
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
    """Open an interactive fuzzy-searchable menu of all DevFlow commands.

    Selecting a command prints the equivalent raw CLI invocation before running
    it — teaching users the full syntax as they go.

    Examples
    --------
    devflow menu
    devflow menu mig
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
        ("DevFlow Command Palette", "bold white"),
        ("\nSearch and run any DevFlow CLI command instantly.\n\n", Theme.MUTED),
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
        f"devflow {selected}",
    )

    console.print(
        f"\n[{Theme.MUTED}]Running:[/{Theme.MUTED}] [{Theme.PRIMARY}]{example_cmd}[/{Theme.PRIMARY}]\n"
    )

    # Execute the example command by splitting and running as a subprocess
    parts = example_cmd.split()
    # Replace "devflow" with actual executable path for reliability
    parts[0] = sys.executable
    parts.insert(1, "-m")
    parts.insert(2, "devflow.main")

    # Actually launch devflow <subcommand> — propagate exit code
    result = subprocess.run([sys.executable, "-m", "devflow.main"] + parts[3:])
    raise typer.Exit(result.returncode)
