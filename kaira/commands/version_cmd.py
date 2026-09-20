"""API Versioning command group."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.config import get_config
from kaira.console import console
from kaira.core.parser import camel_to_snake

app = typer.Typer(help="API Versioning and deprecation commands.")


@app.callback(invoke_without_command=True)
def version_main_callback(ctx: typer.Context) -> None:
    """Show Khaira version when called without subcommands."""
    if ctx.invoked_subcommand is None:
        from kaira import __version__

        console.print(
            Panel(
                f"[bold cyan]Khaira[/bold cyan] (Kaira) v[bold]{__version__}[/bold]",
                border_style="cyan",
            )
        )


@app.command("create")
def version_create(
    version: Annotated[str, typer.Argument(help="Version name, e.g. v1, v2")],
) -> None:
    """Create a versioned API subdirectory structure."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    # e.g. api/v1/routers/
    api_dir = output_root / "api" / version / "routers"
    api_dir.mkdir(parents=True, exist_ok=True)
    (output_root / "api" / "__init__.py").touch(exist_ok=True)
    (output_root / "api" / version / "__init__.py").touch(exist_ok=True)
    (api_dir / "__init__.py").touch(exist_ok=True)

    console.print(
        f"  [green bold]✓[/green bold]  Scaffolding created: [cyan]{api_dir}[/cyan]"
    )
    console.print(
        Panel(
            f"[green]API version {version} structure initialized successfully![/green]",
            title="Khaira — API Versioning",
            border_style="green",
        )
    )


@app.command("migrate")
def version_migrate(
    model_name: Annotated[str, typer.Argument(help="Model name to migrate.")],
    from_version: Annotated[
        str, typer.Option("--from", help="Source version, e.g. v1")
    ],
    to_version: Annotated[str, typer.Option("--to", help="Target version, e.g. v2")],
) -> None:
    """Copy a model's router to a new version and inject deprecation headers into the old version."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    snake = camel_to_snake(model_name)
    src_dir = output_root / "api" / from_version / "routers"
    dest_dir = output_root / "api" / to_version / "routers"

    # Fallback to standard routers dir if not present in api/v1
    src_file = src_dir / f"{snake}_router.py"
    if not src_file.exists():
        # Look in original routers folder
        src_file = output_root / config.routers_dir / f"{snake}_router.py"

    if not src_file.exists():
        console.print(f"[red]Error: Source router file not found:[/red] {src_file}")
        raise typer.Exit(1)

    # Ensure target dir exists
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "__init__.py").touch(exist_ok=True)
    dest_file = dest_dir / f"{snake}_router.py"

    # Copy router to new version
    shutil.copy2(src_file, dest_file)
    console.print(
        f"  [green bold]✓[/green bold]  Migrated router to: [cyan]{dest_file}[/cyan]"
    )

    # Modify the old version router to add Deprecation and Sunset headers
    # Check if the source file is in api/vX/routers
    if src_file.parent.parent.name == from_version:
        v1_content = src_file.read_text(encoding="utf-8")

        # Inject custom middleware-like header addition in endpoints or dependency headers
        # We can add custom Response headers injection
        # Let's import Response from fastapi
        if "from fastapi import" in v1_content:
            v1_content = v1_content.replace(
                "from fastapi import", "from fastapi import Response, "
            )

        # Add headers: Deprecation: true, Sunset: next year
        # Find all def endpoint_name(request: Request, ...) and inject response: Response parameter
        # and then response.headers["Deprecation"] = "true"
        # A simpler way is to inject a custom router decorator or modify the endpoints directly
        lines = v1_content.split("\n")
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if re.match(r"^def \w+\(", line) or re.match(r"^async def \w+\(", line):
                # Simple injection: add response: Response as parameter and write headers
                pass

        # Let's do a cleaner regex replacement: inject headers on endpoint enter
        modified_v1 = re.sub(
            r"(def \w+\([^)]+Depends\(get_service\)\)[^:]*:)",
            r"\1\n    # Deprecation Headers\n    response.headers['Deprecation'] = 'true'\n    response.headers['Sunset'] = '2027-12-31T00:00:00Z'",
            v1_content,
        )
        # Make sure Response is in params
        modified_v1 = re.sub(r"(def \w+\()", r"\1response: Response, ", modified_v1)

        src_file.write_text(modified_v1, encoding="utf-8")
        console.print(
            f"  [green bold]✓[/green bold]  Added Deprecation & Sunset headers to [cyan]{src_file}[/cyan]"
        )


@app.command("list")
def version_list() -> None:
    """List all configured API versions."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    api_root = output_root / "api"
    if not api_root.exists():
        console.print("[yellow]No versioned API folder found under api/[/yellow]")
        return

    versions = [
        d.name for d in api_root.iterdir() if d.is_dir() and d.name.startswith("v")
    ]

    table = Table(title="Khaira — API Versions", border_style="cyan")
    table.add_column("Version", justify="left")
    table.add_column("Routers", justify="left")

    for v in sorted(versions):
        v_routers_dir = api_root / v / "routers"
        routers = []
        if v_routers_dir.exists():
            routers = [
                f.stem.replace("_router", "") for f in v_routers_dir.glob("*_router.py")
            ]
        table.add_row(v, ", ".join(routers) if routers else "None")

    console.print(table)
