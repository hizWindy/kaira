"""Project init command — scaffold a full FastAPI project structure with database & auth wizards."""

from __future__ import annotations

import os
import re
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from devflow.config import save_config, DevFlowConfig
from devflow.console import console
from devflow.core.detector import write_with_check

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Try importing questionary for terminal select wizard
try:
    import questionary
except ImportError:
    questionary = None


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

    console.print("\n⚡ DevFlow — Installing Dependencies\n──────────────────────────────────────────────────")

    installed_count = 0
    failed_count = 0
    skipped_count = 0

    # Package mapping to check already-installed libs cleanly
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
        "aiosqlite": "aiosqlite"
    }

    # Setup the Rich Live display table
    table = Table(box=None, show_header=False)
    table.add_column("status", width=4)
    table.add_column("name", width=30)
    table.add_column("action", width=20)

    with Live(table, refresh_per_second=10) as live:
        for pkg in packages:
            # Extract package name without version pinning for check
            pkg_name = pkg.split("==")[0]
            import_name = pkg_import_map.get(pkg_name, pkg_name)

            # Check if package is already installed
            already_installed = False
            try:
                # First check importlib metadata
                importlib.metadata.version(import_name.replace("_", "-"))
                already_installed = True
            except importlib.metadata.PackageNotFoundError:
                # Fallback to importing check
                if importlib.util.find_spec(import_name) is not None:
                    already_installed = True

            if already_installed:
                skipped_count += 1
                table.add_row("  ✅", f"[green]{pkg}[/green]", "already installed")
                live.update(table)
                continue

            # Display progress status
            row_idx = len(table.rows)
            table.add_row("  ⏳", f"[yellow]{pkg}[/yellow]", "installing...")
            live.update(table)

            # Run pip install silently
            cmd = [sys.executable, "-m", "pip", "install", pkg]
            proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

            if proc.returncode == 0:
                installed_count += 1
                # Update row to complete
                table.columns[0]._cells[row_idx] = "  ✅"
                table.columns[1]._cells[row_idx] = f"[green]{pkg}[/green]"
                table.columns[2]._cells[row_idx] = "[green]installed[/green]"
            else:
                failed_count += 1
                table.columns[0]._cells[row_idx] = "  ❌"
                table.columns[1]._cells[row_idx] = f"[red]{pkg}[/red]"
                table.columns[2]._cells[row_idx] = "[red]failed[/red]"
                # Show safe failure notice at end
                err_msg = proc.stderr.strip().replace("\n", " ")[:60]
                console.print(
                    f"  [red]❌ Failed to install {pkg}[/red]\n"
                    f"     [dim]Reason: {err_msg}[/dim]\n"
                    f"     [dim]Try: pip install {pkg} manually[/dim]"
                )
            live.update(table)

    console.print("──────────────────────────────────────────────────")
    if failed_count == 0:
        console.print("✅ All packages installed successfully!")
    else:
        console.print(f"⚠️  Installation completed with {failed_count} failures.")
    console.print(
        f"──────────────────────────────────────────────────\n"
        f"Installed:  {installed_count} packages\n"
        f"Failed:      {failed_count} packages\n"
        f"Skipped:     {skipped_count} packages (already installed)\n"
        f"──────────────────────────────────────────────────"
    )
    return installed_count, failed_count, skipped_count


def init_project(
    name: str,
    db: str,
    auth: str,
    docker: bool,
    ci: str,
    cwd: Path
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
    write_with_check(cwd / "main.py", main_tmpl.render(**ctx), force=True, non_interactive=True)

    # 2. config/settings.py
    settings_tmpl = env.get_template("env_settings.py.j2")
    write_with_check(cwd / "config" / "settings.py", settings_tmpl.render(**ctx), force=True, non_interactive=True)

    # 3. core/database.py
    if db == "mongodb":
        db_tmpl = env.get_template("database_mongodb.py.j2")
    else:
        db_tmpl = env.get_template("database_async.py.j2")
    write_with_check(cwd / "core" / "database.py", db_tmpl.render(**ctx), force=True, non_interactive=True)

    # 4. core/logger.py
    logger_tmpl = env.get_template("logger.py.j2")
    write_with_check(cwd / "core" / "logger.py", logger_tmpl.render(**ctx), force=True, non_interactive=True)

    # 5. middleware/security.py
    sec_tmpl = env.get_template("security_middleware.py.j2")
    write_with_check(cwd / "middleware" / "security.py", sec_tmpl.render(**ctx), force=True, non_interactive=True)

    # 6. rate_limit.py
    rl_tmpl = env.get_template("rate_limit.py.j2")
    write_with_check(cwd / "rate_limit.py", rl_tmpl.render(**ctx), force=True, non_interactive=True)

    # 7. auth boilerplate
    if auth == "jwt":
        templates = {
            "auth_jwt_dependencies.py.j2": cwd / "auth" / "dependencies.py",
            "auth_jwt_router.py.j2": cwd / "auth" / "router.py",
            "auth_jwt_service.py.j2": cwd / "auth" / "service.py",
            "auth_jwt_schemas.py.j2": cwd / "auth" / "schemas.py",
            "auth_jwt_utils.py.j2": cwd / "auth" / "utils.py",
            "auth_blacklisted_token_model.py.j2": cwd / "models" / "blacklisted_token.py",
        }
        for t_name, t_dest in templates.items():
            write_with_check(t_dest, env.get_template(t_name).render(**ctx), force=True, non_interactive=True)
    elif auth == "oauth2":
        write_with_check(cwd / "auth" / "oauth2.py", env.get_template("auth_oauth2.py.j2").render(**ctx), force=True, non_interactive=True)
    elif auth == "api-key":
        write_with_check(cwd / "auth" / "api_key.py", env.get_template("auth_api_key.py.j2").render(**ctx), force=True, non_interactive=True)

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
            f"DATABASE_URL={db_url}\n"
            f"JWT_SECRET_KEY={secret}\n"
            f"ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n"
            f"DEBUG={'True' if e == 'development' else 'False'}\n"
        )
        write_with_check(cwd / f".env.{e}", env_content, force=True, non_interactive=True)
        if e == "development":
            write_with_check(cwd / ".env", env_content, force=True, non_interactive=True)

    # env.example
    example_content = (
        "APP_ENV=development\n"
        f"APP_NAME={name}\n"
        "DATABASE_URL=sqlite+aiosqlite:///./app.db\n"
        "JWT_SECRET_KEY=your-minimum-32-character-secret-key-here\n"
        "ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n"
        "DEBUG=False\n"
    )
    write_with_check(cwd / ".env.example", example_content, force=True, non_interactive=True)

    # 9. Docker setup
    if docker:
        df_tmpl = env.get_template("docker_dockerfile.j2")
        write_with_check(cwd / "Dockerfile", df_tmpl.render(**ctx), force=True, non_interactive=True)
        
        di_tmpl = env.get_template("docker_ignore.j2")
        write_with_check(cwd / ".dockerignore", di_tmpl.render(**ctx), force=True, non_interactive=True)
        
        dc_tmpl = env.get_template("docker_compose.j2")
        write_with_check(cwd / "docker-compose.yml", dc_tmpl.render(**ctx), force=True, non_interactive=True)
        
        dcp_tmpl = env.get_template("docker_compose_prod.j2")
        write_with_check(cwd / "docker-compose.prod.yml", dcp_tmpl.render(**ctx), force=True, non_interactive=True)

    # 10. CI/CD workflow setup
    if ci == "github":
        gh_dir = cwd / ".github" / "workflows"
        gh_dir.mkdir(parents=True, exist_ok=True)
        write_with_check(gh_dir / "test.yml", env.get_template("ci_github.yml.j2").render(**ctx), force=True, non_interactive=True)
        write_with_check(gh_dir / "security.yml", env.get_template("ci_github_security.yml.j2").render(**ctx), force=True, non_interactive=True)
        write_with_check(gh_dir / "deploy.yml", env.get_template("ci_github_deploy.yml.j2").render(**ctx), force=True, non_interactive=True)
    elif ci == "gitlab":
        write_with_check(cwd / ".gitlab-ci.yml", env.get_template("ci_gitlab.yml.j2").render(**ctx), force=True, non_interactive=True)
    elif ci == "bitbucket":
        write_with_check(cwd / "bitbucket-pipelines.yml", env.get_template("ci_bitbucket.yml.j2").render(**ctx), force=True, non_interactive=True)

    # 11. Gitignore, project README, pyproject.toml
    write_with_check(cwd / ".gitignore", env.get_template("gitignore_project.j2").render(**ctx), force=True, non_interactive=True)
    write_with_check(cwd / "README.md", env.get_template("readme_project.md.j2").render(**ctx), force=True, non_interactive=True)
    write_with_check(cwd / "pyproject.toml", env.get_template("pyproject_generated.toml.j2").render(**ctx), force=True, non_interactive=True)

    # 12. Local DevFlow settings configuration file
    config = DevFlowConfig(
        db_type=db,
        auth_type=auth,
        output_dir="."
    )
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
        console.print(
            "⚡ DevFlow — New Project\n"
            "────────────────────────────────────"
        )
        name = typer.prompt("Project name")
        # Validate project name
        if not re.match(r"^[a-z0-9-]+$", name):
            console.print("[red]Error: Project name must be lowercase, hyphens allowed, no spaces.[/red]")
            raise typer.Exit(1)
    else:
        # Validate project name argument
        if not re.match(r"^[a-z0-9-]+$", name):
            console.print("[red]Error: Project name must be lowercase, hyphens allowed, no spaces.[/red]")
            raise typer.Exit(1)

    project_dir = Path.cwd() / name
    if project_dir.exists():
        console.print(f"[red]Error: Folder '{name}' already exists.[/red]")
        raise typer.Exit(1)

    # Interactive setup wizard
    console.print(
        f"\n⚡ DevFlow — Project Setup: {name}\n"
        "────────────────────────────────────"
    )

    if not db:
        db_choice = select_option("Select database", ["PostgreSQL", "MySQL", "MongoDB", "SQLite"], "PostgreSQL")
        db = db_choice.lower()
    else:
        db = db.lower()
    if db not in valid_dbs:
        console.print(f"[red]Error: Unsupported database '{db}'. Choose: {', '.join(sorted(valid_dbs))}.[/red]")
        raise typer.Exit(1)

    if not auth:
        auth_choice = select_option("Select auth type", ["JWT", "OAuth2", "API Key", "None"], "JWT")
        auth = auth_choice.lower().replace(" ", "-")
    else:
        auth = auth.lower().replace(" ", "-")
    if auth not in valid_auth:
        console.print(f"[red]Error: Unsupported auth type '{auth}'. Choose: {', '.join(sorted(valid_auth))}.[/red]")
        raise typer.Exit(1)

    if docker is None:
        docker = select_confirm("Include Docker?", default=True)

    if ci is None:
        include_ci = select_confirm("Include CI/CD?", default=True)
        if include_ci:
            ci_choice = select_option("Select CI/CD platform", ["GitHub Actions", "GitLab CI", "Bitbucket Pipelines"], "GitHub Actions")
            if "github" in ci_choice.lower():
                ci = "github"
            elif "gitlab" in ci_choice.lower():
                ci = "gitlab"
            else:
                ci = "bitbucket"
        else:
            ci = "none"
    else:
        ci = ci.lower().replace("github-actions", "github").replace("gitlab-ci", "gitlab").replace("bitbucket-pipelines", "bitbucket")
    if ci not in valid_ci:
        console.print(f"[red]Error: Unsupported CI platform '{ci}'. Choose: {', '.join(sorted(valid_ci))}.[/red]")
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
        "passlib[bcrypt]==1.7.4"
    ]

    if db == "postgresql":
        req_packages.extend(["sqlalchemy[asyncio]==2.0.36", "asyncpg==0.30.0", "alembic==1.14.0"])
    elif db == "mysql":
        req_packages.extend(["sqlalchemy[asyncio]==2.0.36", "aiomysql==0.2.0", "alembic==1.14.0"])
    elif db == "mongodb":
        req_packages.extend(["motor==3.6.0", "beanie==1.27.0"])
    elif db == "sqlite":
        req_packages.extend(["sqlalchemy[asyncio]==2.0.36", "aiosqlite==0.20.0", "alembic==1.14.0"])

    if os.environ.get("PYTEST_CURRENT_TEST"):
        console.print("[yellow]Skipping dependency installation while running tests.[/yellow]")
    else:
        install_packages(req_packages)

    console.print(
        f"\n[bold green]✓[/bold green]  Project [bold]{name}[/bold] scaffolded successfully!\n"
        f"[dim]Next steps:[/dim]\n"
        f"  1. [cyan]cd {name}[/cyan]\n"
        f"  2. [cyan]uvicorn main:app --reload[/cyan]"
    )
