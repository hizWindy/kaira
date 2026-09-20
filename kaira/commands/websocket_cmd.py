"""WebSocket scaffolding command group."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from kaira.config import get_config
from kaira.console import console
from kaira.core.detector import write_with_check
from kaira.core.parser import camel_to_snake

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="WebSocket scaffolding commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("generate")
def websocket_generate(
    channel_name: Annotated[
        str, typer.Argument(help="Name of the WebSocket channel, e.g. Chat")
    ],
    ws_type: Annotated[
        str, typer.Option("--type", help="Boilerplate type: chat, notifications")
    ] = "chat",
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files.")
    ] = False,
) -> None:
    """Generate secure WebSocket router, connection manager, and message schemas."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    ws_dir = output_root / "websockets"
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "__init__.py").touch(exist_ok=True)

    env = _get_env()
    snake = camel_to_snake(channel_name)
    ctx = {
        "channel_name": channel_name,
        "snake_name": snake,
        "ws_type": ws_type,
    }

    # Scaffold manager.py, router.py, schemas.py
    templates = {
        "ws_manager.py.j2": ws_dir / "manager.py",
        "ws_router.py.j2": ws_dir / f"{snake}_router.py",
        "ws_schemas.py.j2": ws_dir / f"{snake}_schemas.py",
    }

    for tmpl_name, out_path in templates.items():
        tmpl = env.get_template(tmpl_name)
        content = tmpl.render(**ctx)
        write_with_check(out_path, content, force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")

    console.print(
        Panel(
            f"[green]WebSocket ({ws_type}) scaffolding complete for {channel_name}![/green]\n"
            "Features JWT auth on handshake, connection rate limits, and output escaping.",
            title="Khaira — WebSockets",
            border_style="green",
        )
    )
