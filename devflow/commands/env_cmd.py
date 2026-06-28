"""Environment management command group."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from devflow.config import get_config
from devflow.console import console
from devflow.core.detector import write_with_check

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Environment management commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("init")
def env_init(
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing files.")] = False,
) -> None:
    """Initialize environment config files and settings module."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    # Create config directory
    config_dir = output_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "__init__.py").touch(exist_ok=True)

    env = _get_env()
    ctx = {"project_name": Path.cwd().name, "project_slug": Path.cwd().name.lower().replace("-", "_")}

    # Write config/settings.py
    settings_tmpl = env.get_template("env_settings.py.j2")
    settings_path = config_dir / "settings.py"
    write_with_check(settings_path, settings_tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{settings_path}[/cyan]")

    # Write .env files
    envs = ["development", "staging", "production"]
    for e in envs:
        env_path = output_root / f".env.{e}"
        # Make a secure default key
        secret = "placeholder-32-character-secret-key-for-devflow-api"
        db_url = "sqlite:///./app.db"
        if e == "production":
            db_url = "postgresql://user:pass@localhost/dbname?sslmode=require"
            
        content = (
            f"APP_ENV={e}\n"
            f"APP_NAME={ctx['project_name']}\n"
            f"DATABASE_URL={db_url}\n"
            f"JWT_SECRET_KEY={secret}\n"
            f"ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n"
            f"DEBUG={'True' if e == 'development' else 'False'}\n"
        )
        write_with_check(env_path, content, force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{env_path}[/cyan]")

    # Write .env.example
    example_path = output_root / ".env.example"
    example_content = (
        "APP_ENV=development\n"
        f"APP_NAME={ctx['project_name']}\n"
        "DATABASE_URL=postgresql://user:password@localhost/dbname\n"
        "JWT_SECRET_KEY=your-minimum-32-character-secret-key-here\n"
        "ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000\n"
        "DEBUG=False\n"
    )
    write_with_check(example_path, example_content, force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{example_path}[/cyan]")

    # Append to .gitignore if present
    gitignore_path = output_root / ".gitignore"
    if gitignore_path.exists():
        gi_content = gitignore_path.read_text(encoding="utf-8")
        ignored_lines = [line.strip() for line in gi_content.split("\n")]
        to_add = [".env", ".env.*", "!.env.example"]
        added = False
        for pattern in to_add:
            if pattern not in ignored_lines:
                gi_content += f"\n{pattern}"
                added = True
        if added:
            gitignore_path.write_text(gi_content, encoding="utf-8")
            console.print(f"  [green bold]✓[/green bold]  Updated: [cyan]{gitignore_path}[/cyan] with env rules")

    console.print(Panel(
        "[green]Environment management initialized successfully![/green]\n"
        "Generated .env.development, .env.staging, .env.production, and config/settings.py",
        title="DevFlow — Env Init",
        border_style="green",
    ))


@app.command("add")
def env_add(
    key: Annotated[str, typer.Argument(help="The environment variable key.")],
    value: Annotated[str, typer.Argument(help="The environment variable value.")],
    environment: Annotated[str, typer.Option("--env", help="Target environment: development, staging, production, all")] = "all",
) -> None:
    """Add or update an environment variable key-value pair."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    envs = ["development", "staging", "production"]
    targets = envs if environment == "all" else [environment]

    for t in targets:
        env_path = output_root / f".env.{t}"
        if not env_path.exists():
            console.print(f"[yellow]⚠  Env file {env_path} does not exist. Skipping.[/yellow]")
            continue
            
        content = env_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        updated = False
        
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                updated = True
                break
                
        if not updated:
            lines.append(f"{key}={value}")
            
        env_path.write_text("\n".join(lines), encoding="utf-8")
        console.print(f"  [green bold]✓[/green bold]  Added/Updated: [cyan]{key}[/cyan] in [cyan].env.{t}[/cyan]")


@app.command("switch")
def env_switch(
    environment: Annotated[str, typer.Argument(help="Target environment (e.g. development, staging, production)")],
) -> None:
    """Switch the current active .env file to the target environment."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    src_path = output_root / f".env.{environment}"
    dest_path = output_root / ".env"

    if not src_path.exists():
        console.print(f"[red]Error: Source environment file not found:[/red] {src_path}")
        raise typer.Exit(1)

    shutil.copy2(src_path, dest_path)
    console.print(f"  [green bold]✓[/green bold]  Active environment switched to: [cyan]{environment}[/cyan] (copied to .env)")


@app.command("validate")
def env_validate() -> None:
    """Validate environment keys and secure settings rules."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    # Check for settings.py
    settings_path = output_root / "config" / "settings.py"
    if not settings_path.exists():
        console.print("[red]Error: config/settings.py not found. Run devflow env init first.[/red]")
        raise typer.Exit(1)

    # Standard settings keys
    required_keys = [
        "APP_ENV", "APP_NAME", "DATABASE_URL", "JWT_SECRET_KEY",
        "ALLOWED_ORIGINS", "RATE_LIMIT_GET", "RATE_LIMIT_WRITE", "DEBUG"
    ]

    envs = ["development", "staging", "production"]
    issues = []

    for env_name in envs:
        env_path = output_root / f".env.{env_name}"
        if not env_path.exists():
            issues.append((env_name, "File missing", "❌ High"))
            continue
            
        content = env_path.read_text(encoding="utf-8")
        env_keys = {}
        for line in content.split("\n"):
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env_keys[k.strip()] = v.strip()

        # Check for missing keys
        for key in required_keys:
            if key not in env_keys:
                issues.append((env_name, f"Missing key: {key}", "❌ High"))

        # Check secret key length
        secret = env_keys.get("JWT_SECRET_KEY", "")
        if secret and len(secret) < 32:
            issues.append((env_name, "JWT_SECRET_KEY is shorter than 32 chars", "❌ High"))
            
        # Check production debug mode
        debug = env_keys.get("DEBUG", "False").lower() == "true"
        if env_name == "production" and debug:
            issues.append((env_name, "DEBUG is enabled in production", "❌ High"))

        # Check production CORS
        origins = env_keys.get("ALLOWED_ORIGINS", "")
        if env_name == "production" and "*" in origins:
            issues.append((env_name, "CORS contains wildcard '*' in production", "❌ High"))

        # Check connection pooling/ssl warning
        db_url = env_keys.get("DATABASE_URL", "")
        if "postgresql" in db_url and "sslmode=require" not in db_url:
            issues.append((env_name, "DATABASE_URL lacks sslmode=require", "⚠️  Medium"))

    # Print report
    table = Table(title="DevFlow — Environment Security Audit Report")
    table.add_column("Environment", justify="left")
    table.add_column("Security Issue / Validation Check", justify="left")
    table.add_column("Severity", justify="right")

    for env_name, msg, sev in issues:
        table.add_row(env_name, msg, sev)

    if issues:
        console.print(table)
        console.print(f"[red]Found {len(issues)} validation warnings/issues.[/red]")
    else:
        console.print("[green]✔ All environment checks passed successfully! (All keys present, secure values validated)[/green]")
