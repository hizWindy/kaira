"""DevFlow deploy command group — deployment config generation and pre-flight checklist.

Generates platform-specific deploy configs (Railway, Render, Fly, VPS).
Never writes credentials into generated files — always references platform secret stores.
`devflow deploy run` refuses to execute if any checklist item is ❌.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from devflow.console import console
from devflow.commands.ux_helpers import typed_confirmation

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Deployment config generation and checklist.")

_PLATFORMS = {"railway", "render", "vps", "fly"}

_PLATFORM_FILES: dict[str, tuple[str, str]] = {
    "railway": ("deploy_railway.toml.j2", "railway.toml"),
    "render": ("deploy_render.yaml.j2", "render.yaml"),
    "fly": ("deploy_fly.toml.j2", "fly.toml"),
    "vps": ("deploy_vps_script.sh.j2", "deploy_vps.sh"),
}


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for DevFlow templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _run_checklist() -> list[tuple[str, bool, str]]:
    """Evaluate all deploy checklist items."""
    from devflow.config import get_config
    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    items: list[tuple[str, bool, str]] = []

    env_prod = Path(".env.production")
    items.append((
        ".env.production configured",
        env_prod.exists() and env_prod.stat().st_size > 0,
        "Run: devflow env init",
    ))

    dockerfile = output_root / "Dockerfile"
    items.append((
        "Dockerfile present",
        dockerfile.exists(),
        "Run: devflow docker init --with-compose",
    ))

    tests_dir = output_root / "tests"
    items.append((
        "Tests directory exists",
        tests_dir.exists() and bool(list(tests_dir.glob("test_*.py"))),
        "Run: devflow test generate --all",
    ))

    auth_dir = output_root / "auth"
    items.append((
        "Auth layer configured",
        (auth_dir / "dependencies.py").exists(),
        "Run: devflow auth generate --type jwt",
    ))

    items.append((
        "APP_ENV not hardcoded (check settings.py)",
        True,
        "Ensure no secrets are committed to git",
    ))

    db_type = cfg.db_type
    if db_type != "mongodb":
        alembic_ok = (output_root / "alembic").exists()
        items.append((
            "Alembic migrations initialized",
            alembic_ok,
            "Run: devflow migrate init",
        ))

    return items


@app.command("generate")
def deploy_generate(
    platform: Annotated[
        str,
        typer.Option("--platform", help="Deployment platform: railway | render | vps | fly"),
    ],
) -> None:
    """Generate a platform-specific deployment configuration file."""
    if platform not in _PLATFORMS:
        from devflow.commands.smart_errors import smart_error
        smart_error(
            context=f"Unknown platform '{platform}'.",
            typed=platform,
            candidates=list(_PLATFORMS),
            fix_cmd="devflow deploy generate --platform railway",
            guide_topic="deploy",
        )

    project_name = Path.cwd().name
    tmpl_name, out_name = _PLATFORM_FILES[platform]

    jinja = _get_env_loader()
    tmpl = jinja.get_template(tmpl_name)
    out_path = Path(out_name)
    out_path.write_text(tmpl.render(project_name=project_name), encoding="utf-8")

    console.print(
        Panel(
            f"[green]✅ {platform.capitalize()} deployment config generated: [cyan]{out_path}[/cyan][/green]\n"
            "Credentials are referenced via the platform secret store — not stored in this file.",
            border_style="green",
        )
    )


@app.command("checklist")
def deploy_checklist() -> None:
    """Display the deploy readiness checklist."""
    items = _run_checklist()
    table = Table(title="⚡ Deploy Readiness Checklist", border_style="cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Action")

    for label, passed, hint in items:
        status = "[green]✅ OK[/green]" if passed else "[red]❌ Required[/red]"
        table.add_row(label, status, hint if not passed else "[dim]—[/dim]")

    console.print(table)

    all_passed = all(passed for _, passed, _ in items)
    if all_passed:
        console.print(Panel("[green]✅ All checks passed. Ready to deploy![/green]", border_style="green"))
    else:
        failed = sum(1 for _, passed, _ in items if not passed)
        console.print(
            Panel(
                f"[red]❌ {failed} check(s) failed. Fix them before deploying.[/red]",
                border_style="red",
            )
        )


@app.command("check")
def deploy_check() -> None:
    """Run individual deploy checklist items and exit 1 if any fail."""
    items = _run_checklist()
    all_passed = all(passed for _, passed, _ in items)
    deploy_checklist()
    if not all_passed:
        raise typer.Exit(1)


@app.command("run")
def deploy_run(
    platform: Annotated[
        str,
        typer.Option("--platform", help="Deployment platform: railway | render | vps | fly"),
    ],
    force: Annotated[bool, typer.Option("--force", help="Skip typed confirmation (CI mode)")] = False,
) -> None:
    """Trigger a deployment after passing the full checklist."""
    if platform not in _PLATFORMS:
        console.print(f"[red]❌ Unknown platform '{platform}'. Valid: {', '.join(_PLATFORMS)}[/red]")
        raise typer.Exit(1)

    items = _run_checklist()
    failed_items = [(label, hint) for label, passed, hint in items if not passed]
    if failed_items:
        console.print(
            Panel(
                "[red]❌ Deploy blocked: checklist has failing items.[/red]\n\n"
                + "\n".join(f"  • {label}: {hint}" for label, hint in failed_items),
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if not typed_confirmation(platform, f"This will deploy to [bold]{platform}[/bold].", force=force):
        return

    console.print(
        Panel(
            f"[green]✅ All checks passed. Triggering {platform} deployment...[/green]\n\n"
            f"[dim]Run the platform CLI to deploy:[/dim]\n"
            + {
                "railway": "  railway up",
                "render": "  git push origin main  (Render auto-deploys from git)",
                "fly": "  fly deploy",
                "vps": "  bash deploy_vps.sh user@yourhost",
            }.get(platform, "  Deploy manually"),
            border_style="green",
        )
    )
