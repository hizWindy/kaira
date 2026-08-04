"""Kaira middleware command group — custom middleware scaffolding and management.

Security rules:
- Core security middleware (SecurityHeadersMiddleware, CORSMiddleware, rate limit handler)
  can NEVER be removed.
- New middleware is always registered AFTER core security middleware.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Middleware scaffolding and management.")

_PROTECTED_MIDDLEWARE = {
    "SecurityHeadersMiddleware",
    "CORSMiddleware",
    "RateLimitExceptionHandler",
}


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _scan_middleware(output_root: Path) -> list[str]:
    """Scan the middleware directory for registered middleware names."""
    mw_dir = output_root / "middleware"
    names: list[str] = []
    if not mw_dir.exists():
        return names
    for py_file in mw_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for match in re.finditer(r"class\s+(\w+Middleware)\b", content):
            names.append(match.group(1))
    return names


@app.command("add")
def middleware_add(
    name: Annotated[
        str,
        typer.Argument(help="PascalCase middleware class name, e.g. LoggingMiddleware"),
    ],
    timeout: Annotated[
        int, typer.Option("--timeout", help="Request timeout in seconds")
    ] = 30,
) -> None:
    """Scaffold a new custom middleware class."""
    if not name[0].isupper():
        console.print(
            "[red]❌ Middleware name must be PascalCase, e.g. LoggingMiddleware[/red]"
        )
        raise typer.Exit(1)

    if name in _PROTECTED_MIDDLEWARE:
        console.print(
            Panel(
                f"[red]❌ Blocked: [bold]{name}[/bold] is a core security middleware and cannot be overwritten.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    mw_dir = output_root / "middleware"
    mw_dir.mkdir(parents=True, exist_ok=True)
    (mw_dir / "__init__.py").touch(exist_ok=True)

    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    out_path = mw_dir / f"{snake}.py"

    jinja = _get_env_loader()
    tmpl = jinja.get_template("middleware_custom.py.j2")
    out_path.write_text(
        tmpl.render(middleware_name=name, timeout=timeout),
        encoding="utf-8",
    )
    console.print(f"  [green]✅[/green] Generated: [cyan]{out_path}[/cyan]")
    console.print(
        Panel(
            f"[green]✅ {name} generated.[/green]\n\n"
            "Register in main.py AFTER core security middleware:\n"
            f"  [cyan]app.add_middleware({name})[/cyan]",
            border_style="green",
        )
    )


@app.command("list")
def middleware_list() -> None:
    """List all middleware files registered in the project."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir

    all_mw = list(_PROTECTED_MIDDLEWARE) + _scan_middleware(output_root)
    seen: set[str] = set()
    ordered: list[str] = []
    for m in all_mw:
        if m not in seen:
            seen.add(m)
            ordered.append(m)

    table = Table(title="⚡ Registered Middleware", border_style="cyan")
    table.add_column("Order", style="dim")
    table.add_column("Class Name", style="bold")
    table.add_column("Protected")

    for i, name in enumerate(ordered, 1):
        protected = (
            "[green]🔒 Yes[/green]"
            if name in _PROTECTED_MIDDLEWARE
            else "[dim]No[/dim]"
        )
        table.add_row(str(i), name, protected)

    console.print(table)


@app.command("remove")
def middleware_remove(
    name: Annotated[str, typer.Argument(help="Middleware class name to remove")],
) -> None:
    """Remove a custom middleware file."""
    if name in _PROTECTED_MIDDLEWARE:
        console.print(
            Panel(
                f"[red]❌ Blocked: core security middleware cannot be removed.\n\n"
                f"[bold]{name}[/bold] is required for application security.\n"
                "Removing it would expose the application to attacks.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    mw_path = output_root / "middleware" / f"{snake}.py"

    if not mw_path.exists():
        console.print(f"[yellow]Middleware file not found: {mw_path}[/yellow]")
        raise typer.Exit(1)

    mw_path.unlink()
    console.print(f"[green]✅ Removed: [cyan]{mw_path}[/cyan][/green]")
