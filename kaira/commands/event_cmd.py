"""Kaira event command group — FastAPI lifespan event scaffolding.

Generates events/startup.py and events/shutdown.py. Registers them via the
FastAPI lifespan context manager — NOT the deprecated @app.on_event decorator.
Only calls init_cache() if core/cache.py has been generated.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from kaira.console import console

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="FastAPI lifespan event scaffolding.")


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _cache_enabled(output_root: Path) -> bool:
    """Check whether cache has been initialised in this project."""
    return (output_root / "core" / "cache.py").exists()


@app.command("generate")
def event_generate(
    event_type: Annotated[
        str,
        typer.Argument(help="Event type: startup | shutdown"),
    ],
) -> None:
    """Generate a FastAPI lifespan startup or shutdown event handler."""
    valid = {"startup", "shutdown"}
    if event_type not in valid:
        from kaira.commands.smart_errors import smart_error
        smart_error(
            context=f"Unknown event type '{event_type}'.",
            typed=event_type,
            candidates=list(valid),
            fix_cmd="kaira event generate startup",
            guide_topic="event",
        )

    from kaira.config import get_config
    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    events_dir = output_root / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (events_dir / "__init__.py").touch(exist_ok=True)

    cache_on = _cache_enabled(output_root)
    jinja = _get_env_loader()
    tmpl_name = f"events_{event_type}.py.j2"
    out_path = events_dir / f"{event_type}.py"

    tmpl = jinja.get_template(tmpl_name)
    out_path.write_text(
        tmpl.render(
            project_name=Path.cwd().name,
            cache_enabled=cache_on,
        ),
        encoding="utf-8",
    )
    console.print(f"  [green]✅[/green] Generated: [cyan]{out_path}[/cyan]")

    if cache_on:
        console.print("  [dim]ℹ️  init_cache() will be called on startup (core/cache.py detected)[/dim]")
    else:
        console.print("  [dim]ℹ️  Cache not detected — init_cache() not included. Run kaira cache init first.[/dim]")

    lifespan_snippet = (
        "from contextlib import asynccontextmanager\n"
        "from events.startup import on_startup\n"
        "from events.shutdown import on_shutdown\n\n"
        "@asynccontextmanager\n"
        "async def lifespan(app):\n"
        "    await on_startup()\n"
        "    yield\n"
        "    await on_shutdown()\n\n"
        "app = FastAPI(lifespan=lifespan)\n"
    ) if event_type == "startup" else (
        "# Add on_shutdown to your lifespan context manager:\n"
        "from events.shutdown import on_shutdown\n"
    )

    console.print(
        Panel(
            f"[green]✅ {event_type.capitalize()} event generated.[/green]\n\n"
            "[dim]Register in main.py:[/dim]\n"
            + lifespan_snippet,
            border_style="green",
        )
    )
