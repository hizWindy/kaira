"""Kaira health-endpoint command group — /health route scaffolding.

The generated route is intentionally unauthenticated (monitoring probes must
reach it without credentials). It never leaks connection strings, dependency
versions, or stack traces. Rate-limited at ~300/min so probes don't 429.
Cache check is only included when core/cache.py is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from kaira.console import console
from kaira.commands.ux_helpers import print_next_steps

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Generate a /health monitoring endpoint.")


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("generate")
def health_endpoint_generate() -> None:
    """Generate a /health monitoring endpoint.

    The endpoint:
    - Is unauthenticated (probes must not require credentials)
    - Never leaks connection strings, versions, or stack traces
    - Includes a cache check only if core/cache.py exists
    - Is rate-limited at ~300/min via slowapi
    """
    from kaira.config import get_config
    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir

    routers_dir = output_root / cfg.routers_dir
    routers_dir.mkdir(parents=True, exist_ok=True)

    health_path = routers_dir / "health_router.py"
    if health_path.exists():
        console.print(
            Panel(
                f"[yellow]{health_path} already exists. Delete it first to regenerate.[/yellow]",
                border_style="yellow",
            )
        )
        return

    cache_enabled = (output_root / "core" / "cache.py").exists()

    jinja = _get_env_loader()
    tmpl = jinja.get_template("health_router.py.j2")
    health_path.write_text(
        tmpl.render(
            project_name=Path.cwd().name,
            cache_enabled=cache_enabled,
        ),
        encoding="utf-8",
    )
    console.print(f"  [green]✅[/green] Generated: [cyan]{health_path}[/cyan]")

    if cache_enabled:
        console.print("  [dim]ℹ️  Cache check included (core/cache.py detected)[/dim]")
    else:
        console.print("  [dim]ℹ️  Cache check not included (run kaira cache init to enable)[/dim]")

    console.print(
        Panel(
            "[green]✅ /health endpoint generated.[/green]\n\n"
            "Register in main.py:\n"
            "  [cyan]from routers.health_router import router as health_router[/cyan]\n"
            "  [cyan]app.include_router(health_router)[/cyan]\n\n"
            "[dim]⚠️  Do not add auth dependencies to this router.[/dim]",
            border_style="green",
        )
    )

    next_steps: list[str] = []
    if not cache_enabled:
        next_steps.append("[cyan]kaira cache init[/cyan] — enable cache check in /health")
    next_steps.append("[cyan]kaira api test GET /health[/cyan] — test the endpoint")
    print_next_steps(next_steps)
