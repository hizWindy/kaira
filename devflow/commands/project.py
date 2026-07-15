"""Project init command — scaffold a full FastAPI project structure with database & auth wizards."""

from __future__ import annotations

import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Optional

import typer
from jinja2 import Environment, FileSystemLoader
import time

from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.columns import Columns

from devflow.config import DevFlowConfig
from devflow.console import console
from devflow.core.detector import write_with_check

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Try importing questionary for terminal select wizard
try:
    import questionary
except ImportError:
    questionary = None  # type: ignore[assignment]


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _pascal_to_slug(name: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def select_option(message: str, choices: list[str], default: str) -> str:
    """Helper to select an option via questionary or fallback to text selection."""
    if questionary is not None:
        try:
            val = questionary.select(message, choices=choices, default=default).ask()
            if val is not None:
                return val
        except Exception:
            pass

    # Fallback interactive selection
    console.print(f"\n[cyan]? {message}[/cyan]")
    for i, choice in enumerate(choices, 1):
        indicator = "  "
        if choice == default:
            indicator = "> "
        console.print(f" {indicator}{i}) {choice}")

    while True:
        val = typer.prompt(f"Select option (1-{len(choices)})", default="1")
        try:
            idx = int(val) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        console.print("[red]Invalid selection. Try again.[/red]")


def select_confirm(message: str, default: bool = True) -> bool:
    """Helper to ask a yes/no question."""
    if questionary is not None:
        try:
            val = questionary.confirm(message, default=default).ask()
            if val is not None:
                return val
        except Exception:
            pass
    return typer.confirm(message, default=default)


def install_packages(packages: list[str]) -> tuple[int, int, int]:
    """
    Install python packages silently and display a Rich live progress table.

    Returns:
        tuple[int, int, int]: (installed_count, failed_count, skipped_count)
    """
    import importlib.util
    import importlib.metadata
    from rich import box as rich_box

    # ── Header ──────────────────────────────────────────────────────────────
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"  [bold white]Installing [cyan]{len(packages)}[/cyan] package(s) "
                f"into your project environment[/bold white]\n"
                f"  [dim]DevFlow will skip packages already present on this machine.[/dim]"
            ),
            title="[bold cyan]⚡  DevFlow  —  Dependency Installer[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()

    installed_count = 0
    failed_count = 0
    skipped_count = 0
    start_time = time.monotonic()
    failed_details: list[tuple[str, str]] = []

    # Package → importable-name mapping
    pkg_import_map = {
        "fastapi": "fastapi",
        "uvicorn[standard]": "uvicorn",
        "sqlalchemy[asyncio]": "sqlalchemy",
        "alembic": "alembic",
        "pydantic": "pydantic",
        "pydantic-settings": "pydantic_settings",
        "slowapi": "slowapi",
        "loguru": "loguru",
        "python-jose[cryptography]": "jose",
        "passlib[bcrypt]": "passlib",
        "python-dotenv": "dotenv",
        "bcrypt": "bcrypt",
        "asyncpg": "asyncpg",
        "aiomysql": "aiomysql",
        "motor": "motor",
        "beanie": "beanie",
        "aiosqlite": "aiosqlite",
    }

    # ── Build the live package-status table ─────────────────────────────────
    def _make_table() -> Table:
        t = Table(
            box=rich_box.ROUNDED,
            border_style="bright_black",
            show_header=True,
            header_style="bold bright_white on grey23",
            expand=True,
            padding=(0, 1),
        )
        t.add_column("  ", width=3, no_wrap=True)  # icon
        t.add_column("Package", style="bold", ratio=3)  # name
        t.add_column("Status", ratio=2)  # status label
        t.add_column("Note", style="dim", ratio=3)  # extra info
        return t

    table = _make_table()

    with Live(
        table, console=console, refresh_per_second=12, vertical_overflow="visible"
    ) as live:
        for pkg in packages:
            pkg_name = re.split(r"[><=!\[]", pkg)[0].strip()
            import_name = pkg_import_map.get(pkg, pkg_name)

            # ── Already-installed check ──────────────────────────────────
            already_installed = False
            installed_version: str | None = None
            try:
                installed_version = importlib.metadata.version(
                    import_name.replace("_", "-")
                )
                already_installed = True
            except importlib.metadata.PackageNotFoundError:
                if importlib.util.find_spec(import_name) is not None:
                    already_installed = True

            if already_installed:
                skipped_count += 1
                ver_note = f"v{installed_version}" if installed_version else "present"
                table.add_row(
                    "[green]✔[/green]",
                    f"[green]{pkg}[/green]",
                    "[dim green]Already installed[/dim green]",
                    f"[dim]{ver_note}[/dim]",
                )
                live.update(table)
                continue

            # ── Pending row (spinner effect via repeated update) ─────────
            row_idx = len(table.rows)
            table.add_row(
                "[yellow]⟳[/yellow]",
                f"[yellow]{pkg}[/yellow]",
                "[yellow]Installing…[/yellow]",
                "[dim]fetching from PyPI[/dim]",
            )
            live.update(table)

            t0 = time.monotonic()
            cmd = [sys.executable, "-m", "pip", "install", pkg]
            proc = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
            )
            elapsed = time.monotonic() - t0

            if proc.returncode == 0:
                installed_count += 1
                # Try to fetch the version we just installed
                try:
                    new_ver = importlib.metadata.version(import_name.replace("_", "-"))
                    ver_note = f"v{new_ver}"
                except Exception:
                    ver_note = "installed"
                table.columns[0]._cells[row_idx] = "[bold green]✔[/bold green]"
                table.columns[1]._cells[row_idx] = f"[bold green]{pkg}[/bold green]"
                table.columns[2]._cells[row_idx] = "[bold green]Installed[/bold green]"
                table.columns[3]._cells[row_idx] = (
                    f"[dim]{ver_note}  ({elapsed:.1f}s)[/dim]"
                )
            else:
                failed_count += 1
                err_msg = (
                    proc.stderr.strip().splitlines()[-1]
                    if proc.stderr.strip()
                    else "unknown error"
                )
                err_short = err_msg[:55]
                failed_details.append((pkg, err_msg))
                table.columns[0]._cells[row_idx] = "[bold red]✘[/bold red]"
                table.columns[1]._cells[row_idx] = f"[bold red]{pkg}[/bold red]"
                table.columns[2]._cells[row_idx] = "[bold red]Failed[/bold red]"
                table.columns[3]._cells[row_idx] = f"[dim red]{err_short}[/dim red]"

            live.update(table)

    # ── Failure detail block ─────────────────────────────────────────────────
    if failed_details:
        console.print()
        for fpkg, ferr in failed_details:
            console.print(
                Panel(
                    f"[red]{ferr.strip()[:200]}[/red]\n\n"
                    f"[dim]Retry manually:[/dim]  [bold]pip install {fpkg}[/bold]",
                    title=f"[red]✘  Install failed — {fpkg}[/red]",
                    border_style="red",
                    padding=(0, 2),
                )
            )

    # ── Summary panel ───────────────────────────────────────────────────────
    elapsed_total = time.monotonic() - start_time
    console.print()

    summary_table = Table(box=rich_box.SIMPLE, show_header=False, padding=(0, 2))
    summary_table.add_column("", style="bold", width=20)
    summary_table.add_column("", justify="right", width=6)

    summary_table.add_row(
        "[bold green]✔  Installed[/bold green]",
        f"[bold green]{installed_count}[/bold green]",
    )
    summary_table.add_row(
        "[bold dim]⊘  Skipped[/bold dim]",
        f"[dim]{skipped_count}[/dim]",
    )
    if failed_count:
        summary_table.add_row(
            "[bold red]✘  Failed[/bold red]",
            f"[bold red]{failed_count}[/bold red]",
        )
    summary_table.add_row("", "")
    summary_table.add_row(
        "[dim]⏱  Total time[/dim]",
        f"[dim]{elapsed_total:.1f}s[/dim]",
    )

    if failed_count == 0:
        status_line = "[bold green]All packages ready — your project environment is set up![/bold green]"
        border = "green"
        icon = "🎉"
    else:
        status_line = (
            f"[bold yellow]Installation finished with [red]{failed_count}[/red] failure(s). "
            f"See above for details.[/bold yellow]"
        )
        border = "yellow"
        icon = "⚠️ "

    console.print(
        Panel(
            Columns(
                [summary_table, Text.from_markup(f"\n  {status_line}")],
                equal=False,
                expand=True,
            ),
            title=f"[bold]{icon}  Installation Summary[/bold]",
            border_style=border,
            padding=(0, 1),
        )
    )
    console.print()

    return installed_count, failed_count, skipped_count


def init_project(
    name: str, db: str, auth: str, docker: bool, ci: str, cwd: Path
) -> None:
    """Scaffold a FastAPI project with Phase 3 configuration inside named directory."""
    env = _get_env()
    slug = _pascal_to_slug(name)

    # Ensure targeted folders exist
    PROJECT_DIRS = [
        "models",
        "repositories",
        "schemas",
        "services",
        "routers",
        "auth",
        "config",
        "core",
        "middleware",
        "logs",
        "tests",
    ]

    for d in PROJECT_DIRS:
        (cwd / d).mkdir(parents=True, exist_ok=True)
        (cwd / d / "__init__.py").touch(exist_ok=True)

    # Empty logkeep file
    (cwd / "logs" / ".gitkeep").touch(exist_ok=True)

    # Context values for Jinja render
    ctx = {
        "project_name": name,
        "project_slug": slug,
        "db_type": db,
        "auth_type": auth,
        "api_version": "v1",
    }

    # 1. main.py from v3 template
    main_tmpl = env.get_template("main_app_v3.py.j2")
    write_with_check(
        cwd / "main.py", main_tmpl.render(**ctx), force=True, non_interactive=True
    )

    # 2. config/settings.py
    settings_tmpl = env.get_template("env_settings.py.j2")
    write_with_check(
        cwd / "config" / "settings.py",
        settings_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 3. core/database.py
    if db == "mongodb":
        db_tmpl = env.get_template("database_mongodb.py.j2")
    else:
        db_tmpl = env.get_template("database_async.py.j2")
    write_with_check(
        cwd / "core" / "database.py",
        db_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 4. core/logger.py
    logger_tmpl = env.get_template("logger.py.j2")
    write_with_check(
        cwd / "core" / "logger.py",
        logger_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 5. middleware/security.py
    sec_tmpl = env.get_template("security_middleware.py.j2")
    write_with_check(
        cwd / "middleware" / "security.py",
        sec_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 6. rate_limit.py
    rl_tmpl = env.get_template("rate_limit.py.j2")
    write_with_check(
        cwd / "rate_limit.py", rl_tmpl.render(**ctx), force=True, non_interactive=True
    )

    # 7. auth boilerplate
    if auth == "jwt":
        templates = {
            "auth_jwt_dependencies.py.j2": cwd / "auth" / "dependencies.py",
            "auth_jwt_router.py.j2": cwd / "auth" / "router.py",
            "auth_jwt_service.py.j2": cwd / "auth" / "service.py",
            "auth_jwt_schemas.py.j2": cwd / "auth" / "schemas.py",
            "auth_jwt_utils.py.j2": cwd / "auth" / "utils.py",
            "auth_blacklisted_token_model.py.j2": cwd
            / "models"
            / "blacklisted_token.py",
        }
        for t_name, t_dest in templates.items():
            write_with_check(
                t_dest,
                env.get_template(t_name).render(**ctx),
                force=True,
                non_interactive=True,
            )
    elif auth == "oauth2":
        write_with_check(
            cwd / "auth" / "oauth2.py",
            env.get_template("auth_oauth2.py.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
    elif auth == "api-key":
        write_with_check(
            cwd / "auth" / "api_key.py",
            env.get_template("auth_api_key.py.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )

    # 8. static configuration and environment profile templates
    envs = ["development", "staging", "production"]
    for e in envs:
        secret = "placeholder-32-character-secret-key-for-devflow-api"
        db_url = "sqlite+aiosqlite:///./app.db"
        if db == "postgresql":
            db_url = f"postgresql+asyncpg://user:pass@localhost:5432/{slug}"
            if e == "production":
                db_url += "?sslmode=require"
        elif db == "mysql":
            db_url = f"mysql+aiomysql://user:pass@localhost:3306/{slug}"
        elif db == "mongodb":
            db_url = f"mongodb://localhost:27017/{slug}"
            if e == "production":
                db_url = f"mongodb+srv://user:pass@cluster.mongodb.net/{slug}"

        env_content = (
            f"APP_ENV={e}\n"
            f"APP_NAME={name}\n"
            f"# DATABASE_URL={db_url}\n"
            f"# Uncomment and fill in your real credentials before running the app.\n"
            f"JWT_SECRET_KEY={secret}\n"
            f'ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n'
            f"DEBUG={'True' if e == 'development' else 'False'}\n"
        )
        write_with_check(
            cwd / f".env.{e}", env_content, force=True, non_interactive=True
        )
        if e == "development":
            write_with_check(
                cwd / ".env", env_content, force=True, non_interactive=True
            )

    # env.example
    example_content = (
        "APP_ENV=development\n"
        f"APP_NAME={name}\n"
        "# DATABASE_URL=sqlite+aiosqlite:///./app.db\n"
        "# Uncomment and fill in your real credentials before running the app.\n"
        "JWT_SECRET_KEY=your-minimum-32-character-secret-key-here\n"
        'ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n'
        "DEBUG=False\n"
    )
    write_with_check(
        cwd / ".env.example", example_content, force=True, non_interactive=True
    )

    # 9. Docker setup
    if docker:
        df_tmpl = env.get_template("docker_dockerfile.j2")
        write_with_check(
            cwd / "Dockerfile", df_tmpl.render(**ctx), force=True, non_interactive=True
        )

        di_tmpl = env.get_template("docker_ignore.j2")
        write_with_check(
            cwd / ".dockerignore",
            di_tmpl.render(**ctx),
            force=True,
            non_interactive=True,
        )

        dc_tmpl = env.get_template("docker_compose.j2")
        write_with_check(
            cwd / "docker-compose.yml",
            dc_tmpl.render(**ctx),
            force=True,
            non_interactive=True,
        )

        dcp_tmpl = env.get_template("docker_compose_prod.j2")
        write_with_check(
            cwd / "docker-compose.prod.yml",
            dcp_tmpl.render(**ctx),
            force=True,
            non_interactive=True,
        )

    # 10. CI/CD workflow setup
    if ci == "github":
        gh_dir = cwd / ".github" / "workflows"
        gh_dir.mkdir(parents=True, exist_ok=True)
        write_with_check(
            gh_dir / "test.yml",
            env.get_template("ci_github.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
        write_with_check(
            gh_dir / "security.yml",
            env.get_template("ci_github_security.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
        write_with_check(
            gh_dir / "deploy.yml",
            env.get_template("ci_github_deploy.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
    elif ci == "gitlab":
        write_with_check(
            cwd / ".gitlab-ci.yml",
            env.get_template("ci_gitlab.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
    elif ci == "bitbucket":
        write_with_check(
            cwd / "bitbucket-pipelines.yml",
            env.get_template("ci_bitbucket.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )

    # 11. Gitignore, project README, pyproject.toml
    write_with_check(
        cwd / ".gitignore",
        env.get_template("gitignore_project.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )
    write_with_check(
        cwd / "README.md",
        env.get_template("readme_project.md.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )
    write_with_check(
        cwd / "pyproject.toml",
        env.get_template("pyproject_generated.toml.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 12. Local DevFlow settings configuration file
    config = DevFlowConfig(db_type=db, auth_type=auth, output_dir=".")
    # Save config directly inside the project directory
    config_path = cwd / ".devflow.json"
    import json

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def init_command(
    name: Optional[str] = None,
    db: Optional[str] = None,
    auth: Optional[str] = None,
    docker: Optional[bool] = None,
    ci: Optional[str] = None,
) -> None:
    """Entrypoint for devflow init command with wizard setup."""
    valid_dbs = {"postgresql", "mysql", "mongodb", "sqlite"}
    valid_auth = {"jwt", "oauth2", "api-key", "none"}
    valid_ci = {"github", "gitlab", "bitbucket", "none"}

    # Check if we are inside a folder with existing devflow configuration
    # If project name is completely omitted, we trigger the wizard or prompt
    if not name:
        console.print("⚡ DevFlow — New Project\n────────────────────────────────────")
        name = typer.prompt("Project name")
        # Validate project name
        if not re.match(r"^[a-z0-9-]+$", name):
            console.print(
                "[red]Error: Project name must be lowercase, hyphens allowed, no spaces.[/red]"
            )
            raise typer.Exit(1)
    else:
        # Validate project name argument
        if not re.match(r"^[a-z0-9-]+$", name):
            console.print(
                "[red]Error: Project name must be lowercase, hyphens allowed, no spaces.[/red]"
            )
            raise typer.Exit(1)

    project_dir = Path.cwd() / name
    if project_dir.exists():
        console.print(f"[red]Error: Folder '{name}' already exists.[/red]")
        raise typer.Exit(1)

    # Interactive setup wizard
    console.print(
        f"\n⚡ DevFlow — Project Setup: {name}\n────────────────────────────────────"
    )

    if not db:
        db_choice = select_option(
            "Select database",
            ["PostgreSQL", "MySQL", "MongoDB", "SQLite"],
            "PostgreSQL",
        )
        db = db_choice.lower()
    else:
        db = db.lower()
    if db not in valid_dbs:
        console.print(
            f"[red]Error: Unsupported database '{db}'. Choose: {', '.join(sorted(valid_dbs))}.[/red]"
        )
        raise typer.Exit(1)

    if not auth:
        auth_choice = select_option(
            "Select auth type", ["JWT", "OAuth2", "API Key", "None"], "JWT"
        )
        auth = auth_choice.lower().replace(" ", "-")
    else:
        auth = auth.lower().replace(" ", "-")
    if auth not in valid_auth:
        console.print(
            f"[red]Error: Unsupported auth type '{auth}'. Choose: {', '.join(sorted(valid_auth))}.[/red]"
        )
        raise typer.Exit(1)

    if docker is None:
        docker = select_confirm("Include Docker?", default=True)

    if ci is None:
        include_ci = select_confirm("Include CI/CD?", default=True)
        if include_ci:
            ci_choice = select_option(
                "Select CI/CD platform",
                ["GitHub Actions", "GitLab CI", "Bitbucket Pipelines"],
                "GitHub Actions",
            )
            if "github" in ci_choice.lower():
                ci = "github"
            elif "gitlab" in ci_choice.lower():
                ci = "gitlab"
            else:
                ci = "bitbucket"
        else:
            ci = "none"
    else:
        ci = (
            ci.lower()
            .replace("github-actions", "github")
            .replace("gitlab-ci", "gitlab")
            .replace("bitbucket-pipelines", "bitbucket")
        )
    if ci not in valid_ci:
        console.print(
            f"[red]Error: Unsupported CI platform '{ci}'. Choose: {', '.join(sorted(valid_ci))}.[/red]"
        )
        raise typer.Exit(1)

    console.print("────────────────────────────────────")
    console.print(f"✅ Generating {name}...")
    console.print("────────────────────────────────────")

    # Scaffold the project files
    project_dir.mkdir(parents=True, exist_ok=True)
    init_project(name, db, auth, docker, ci, project_dir)

    # Package installation phase
    # Determine DB-specific and Core required packages
    req_packages = [
        "fastapi==0.115.0",
        "uvicorn[standard]==0.29.0",
        "pydantic==2.10.0",
        "pydantic-settings==2.7.0",
        "slowapi==0.1.9",
        "loguru==0.7.2",
        "python-dotenv==1.0.1",
        "bcrypt==4.1.2",
        "python-jose[cryptography]==3.3.0",
        "passlib[bcrypt]==1.7.4",
    ]

    if db == "postgresql":
        req_packages.extend(
            ["sqlalchemy[asyncio]==2.0.36", "asyncpg==0.30.0", "alembic==1.14.0"]
        )
    elif db == "mysql":
        req_packages.extend(
            ["sqlalchemy[asyncio]==2.0.36", "aiomysql==0.2.0", "alembic==1.14.0"]
        )
    elif db == "mongodb":
        req_packages.extend(["motor==3.6.0", "beanie==1.27.0"])
    elif db == "sqlite":
        req_packages.extend(
            ["sqlalchemy[asyncio]==2.0.36", "aiosqlite==0.20.0", "alembic==1.14.0"]
        )

    if os.environ.get("PYTEST_CURRENT_TEST"):
        console.print(
            "[yellow]Skipping dependency installation while running tests.[/yellow]"
        )
    else:
        install_packages(req_packages)

    console.print(
        f"\n[bold green]✓[/bold green]  Project [bold]{name}[/bold] scaffolded successfully!\n"
        f"[dim]Next steps:[/dim]\n"
        f"  1. [cyan]cd {name}[/cyan]\n"
        f"  2. [cyan]devflow run[/cyan]"
    )
