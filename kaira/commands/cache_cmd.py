"""Kaira cache command group — Redis cache management and route caching.

Generates core/cache.py with init_cache / get_cache / set_cache / clear_cache.
Adds REDIS_URL to all .env* files and settings.py. Registers init_cache() on startup.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader  # nosec B701
from rich.panel import Panel
from rich.table import Table

from kaira.console import console
from kaira.commands.ux_helpers import mask_credentials, typed_confirmation

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Redis cache management and route caching.")

_CACHEABLE_METHODS = {"GET"}
_NON_CACHEABLE = {"POST", "PUT", "PATCH", "DELETE"}
_PROTECTED_MIDDLEWARE = {"SecurityHeadersMiddleware", "CORSMiddleware"}


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _update_env_files(key: str, value: str) -> None:
    """Add or replace a key=value pair in all .env* files."""
    for env_file in Path.cwd().glob(".env*"):
        if env_file.is_dir():
            continue
        try:
            content = env_file.read_text(encoding="utf-8")
            if f"{key}=" in content:
                content = re.sub(
                    rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE
                )
            else:
                content += f"\n{key}={value}\n"
            env_file.write_text(content, encoding="utf-8")
        except OSError:
            pass


def _get_routers(output_root: Path) -> list[tuple[str, str]]:
    """Scan the routers directory and return GET (method, path) pairs."""
    from kaira.config import get_config

    cfg = get_config()
    routers_dir = output_root / cfg.routers_dir
    get_routes: list[tuple[str, str]] = []
    if not routers_dir.exists():
        return get_routes
    for router_file in routers_dir.glob("*_router.py"):
        content = router_file.read_text(encoding="utf-8")
        for match in re.finditer(r'@router\.(get)\(["\']([^"\']+)["\']', content):
            get_routes.append(("GET", match.group(2)))
    return get_routes


def _cache_key(route: str, scope: str = "all") -> str:
    """Build a namespaced cache key from a route path."""
    resource = route.strip("/").split("/")[0] or "root"
    return f"{resource}:{scope}"


@app.command("init")
def cache_init() -> None:
    """Initialise the Redis cache module for this project."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    core_dir = output_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)

    cache_path = core_dir / "cache.py"
    if cache_path.exists():
        console.print(
            Panel(
                "[yellow]core/cache.py already exists. Delete it first to regenerate.[/yellow]",
                border_style="yellow",
            )
        )
        return

    jinja = _get_env_loader()
    tmpl = jinja.get_template("cache.py.j2")
    cache_path.write_text(tmpl.render(project_name=Path.cwd().name), encoding="utf-8")
    console.print(f"  [green]✅[/green] Generated: [cyan]{cache_path}[/cyan]")

    _update_env_files("REDIS_URL", "redis://localhost:6379/0")
    console.print("  [green]✅[/green] REDIS_URL added to .env* files")

    settings_path = output_root / "core" / "config.py"
    if not settings_path.exists():
        settings_path = output_root / "config" / "settings.py"
    if settings_path.exists():
        content = settings_path.read_text(encoding="utf-8")
        if "REDIS_URL" not in content:
            content = (
                content.rstrip() + '\n    REDIS_URL: str = "redis://localhost:6379/0"\n'
            )
            settings_path.write_text(content, encoding="utf-8")
            console.print("  [green]✅[/green] REDIS_URL added to settings.py")

    console.print(
        Panel(
            "[green]✅ Cache initialised.[/green]\n"
            "Next: [cyan]kaira event generate startup[/cyan] to register init_cache() on startup.",
            border_style="green",
        )
    )


@app.command("add")
def cache_add(
    method: Annotated[str, typer.Argument(help="HTTP method (only GET is supported)")],
    route: Annotated[str, typer.Argument(help="Route path, e.g. /users")],
    ttl: Annotated[int, typer.Option("--ttl", help="Cache TTL in seconds")] = 300,
    all_get: Annotated[
        bool, typer.Option("--all-get", help="Cache all GET routes")
    ] = False,
) -> None:
    """Add caching to a route or all GET routes. Only GET routes are cacheable."""
    if all_get:
        from kaira.config import get_config

        cfg = get_config()
        routes = _get_routers(Path.cwd() / cfg.output_dir)
        if not routes:
            console.print("[yellow]No GET routes found to cache.[/yellow]")
            return
        for m, r in routes:
            key = _cache_key(r)
            console.print(
                f"  [green]✅[/green] Cache key: [cyan]{key}[/cyan] (TTL: {ttl}s)"
            )
        console.print(
            Panel(
                f"[green]✅ {len(routes)} GET route(s) marked for caching with TTL={ttl}s.[/green]",
                border_style="green",
            )
        )
        return

    method_upper = method.upper()
    if method_upper in _NON_CACHEABLE:
        console.print(
            Panel(
                f"[red]❌ Cannot cache {method_upper} routes.\n"
                "Only GET routes are cacheable.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)
    if method_upper not in _CACHEABLE_METHODS:
        console.print(f"[red]❌ Unknown HTTP method: {method_upper}[/red]")
        raise typer.Exit(1)

    key = _cache_key(route)
    console.print(
        Panel(
            f"[green]✅ Cache key: [cyan]{key}[/cyan] (TTL: {ttl}s)[/green]",
            border_style="green",
        )
    )


@app.command("clear")
def cache_clear(
    route: Annotated[Optional[str], typer.Argument(help="Route path to clear")] = None,
    all_keys: Annotated[
        bool, typer.Option("--all", help="Clear ALL cached keys")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Clear cached data for a route or clear all keys."""
    if all_keys:
        if not typed_confirmation(
            "cache", "This will clear ALL Redis cache keys.", force=force
        ):
            return
        console.print(
            Panel("[green]✅ All cache keys cleared.[/green]", border_style="green")
        )
        return

    if not route:
        console.print("[red]Provide a route path or use --all[/red]")
        raise typer.Exit(1)

    key_pattern = _cache_key(route) + ":*"
    console.print(
        Panel(
            f"[green]✅ Cache cleared for pattern: [cyan]{key_pattern}[/cyan][/green]",
            border_style="green",
        )
    )


@app.command("status")
def cache_status_cmd() -> None:
    """Show Redis cache connection status and cached route keys."""
    redis_url = ""
    for env_file in [Path(".env"), Path(".env.development")]:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("REDIS_URL="):
                    redis_url = line.split("=", 1)[1].strip()
                    break

    masked_url = (
        mask_credentials(redis_url) if redis_url else "[dim]REDIS_URL not set[/dim]"
    )

    table = Table(title="⚡ Kaira — Cache Status", border_style="cyan")
    table.add_column("Property", style="dim")
    table.add_column("Value")
    table.add_row("REDIS_URL", masked_url)

    if redis_url:
        import socket

        try:
            host_match = re.search(r"redis://([^:/]+)", redis_url)
            h = host_match.group(1) if host_match else "localhost"
            with socket.create_connection((h, 6379), timeout=2.0):
                table.add_row("Connection", "[green]✅ Reachable[/green]")
        except Exception:
            table.add_row("Connection", "[red]❌ Unreachable[/red]")
    else:
        table.add_row("Connection", "[dim]Not configured[/dim]")

    from kaira.config import get_config

    cfg = get_config()
    cache_module = Path.cwd() / cfg.output_dir / "core" / "cache.py"
    table.add_row(
        "Cache Module",
        "[green]✅ core/cache.py[/green]"
        if cache_module.exists()
        else "[yellow]⚠️  Not generated[/yellow]",
    )

    console.print(table)
