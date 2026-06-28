"""List command group — list models and routes."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from devflow.config import get_config
from devflow.console import console

app = typer.Typer(help="List generated resources.")


@app.command("models")
def list_models() -> None:
    """List all generated model files in the models directory."""
    config = get_config()
    models_dir = Path.cwd() / config.models_dir

    if not models_dir.exists():
        console.print(f"[yellow]⚠[/yellow]  Models directory not found: [dim]{models_dir}[/dim]")
        raise typer.Exit(0)

    model_files = sorted(
        f for f in models_dir.iterdir()
        if f.suffix == ".py" and f.name != "__init__.py"
    )

    if not model_files:
        console.print("[dim]No model files found.[/dim]")
        return

    table = Table(title=f"Models in [cyan]{models_dir}[/cyan]", border_style="cyan", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="bold cyan")
    table.add_column("Size", style="dim", justify="right")

    for i, f in enumerate(model_files, 1):
        size = f"{f.stat().st_size:,} B"
        table.add_row(str(i), f.name, size)

    console.print(table)
    console.print(f"[dim]{len(model_files)} model(s) found.[/dim]")


@app.command("routes")
def list_routes() -> None:
    """List all generated router endpoints with full prefixed paths, methods, auth, and rate limits."""
    config = get_config()
    routers_dir = Path.cwd() / config.routers_dir

    if not routers_dir.exists():
        console.print(f"[yellow]⚠[/yellow]  Routers directory not found: [dim]{routers_dir}[/dim]")
        raise typer.Exit(0)

    router_files = sorted(
        f for f in routers_dir.iterdir()
        if f.suffix == ".py" and f.name != "__init__.py"
    )

    if not router_files:
        console.print("[dim]No router files found.[/dim]")
        return

    api_version = getattr(config, "api_version", "v1")
    api_prefix = f"/api/{api_version}"

    table = Table(title="DevFlow — Registered API Routes", border_style="cyan", show_lines=True)
    table.add_column("Route", style="bold cyan")
    table.add_column("Method", style="green", width=8)
    table.add_column("Auth", style="bold yellow", justify="center", width=6)
    table.add_column("Rate Limit", style="magenta")

    http_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

    for f in router_files:
        content = f.read_text(encoding="utf-8")
        
        # 1. Parse Router Prefix
        import re
        prefix_match = re.search(r"prefix\s*=\s*[\"']([^\"']+)[\"']", content)
        router_prefix = prefix_match.group(1) if prefix_match else ""
        if not router_prefix.startswith("/"):
            router_prefix = "/" + router_prefix

        # 2. Find all route endpoint blocks
        # We can look for @router.get/post/etc decorators
        # Let's parse them using regex to support multiple decorators per function
        lines = content.split("\n")
        
        # Keep track of active decorators as we scan lines
        current_rate_limit = "—"
        current_auth = "❌"
        
        for idx, line in enumerate(lines):
            line_str = line.strip()
            
            # Match Rate limit decorator
            # e.g., @limiter.limit("20/minute") or @limiter.limit(settings.RATE_LIMIT_GET)
            limit_match = re.match(r"@limiter\.limit\(([^)]+)\)", line_str)
            if limit_match:
                limit_val = limit_match.group(1).strip("\"'")
                # Map setting keys to human-readable strings
                if "RATE_LIMIT_GET" in limit_val:
                    current_rate_limit = "60/min"
                elif "RATE_LIMIT_WRITE" in limit_val:
                    current_rate_limit = "20/min"
                else:
                    current_rate_limit = limit_val.replace("/minute", "/min")
                continue
                
            # Match HTTP Method decorators
            # e.g., @router.get("/", ...)
            for method in http_methods:
                decorator_pat = rf"@router\.{method.lower()}\(\s*[\"']([^\"']*)[\"']"
                route_match = re.match(decorator_pat, line_str)
                if route_match:
                    sub_path = route_match.group(1)
                    if sub_path == "/":
                        sub_path = ""
                    elif not sub_path.startswith("/") and sub_path:
                        sub_path = "/" + sub_path
                        
                    full_route = f"{api_prefix}{router_prefix}{sub_path}"
                    # Normalize double slashes
                    full_route = re.sub(r"/+", "/", full_route)

                    # Look ahead a few lines for auth guard parameters
                    # Check if 'current_user' or 'get_current_user' or 'validate_api_key' appears in the function signature
                    has_auth = False
                    for offset in range(1, 10):
                        if idx + offset < len(lines):
                            next_line = lines[idx + offset]
                            if "def " in next_line:
                                # We reached function start, let's scan signature
                                sig_lines = []
                                for sig_offset in range(0, 10):
                                    if idx + offset + sig_offset < len(lines):
                                        sig_lines.append(lines[idx + offset + sig_offset])
                                        if "):" in lines[idx + offset + sig_offset]:
                                            break
                                sig_str = "".join(sig_lines)
                                if "get_current_user" in sig_str or "validate_api_key" in sig_str:
                                    has_auth = True
                                break
                    
                    auth_str = "✅" if has_auth else "❌"
                    table.add_row(full_route, method, auth_str, current_rate_limit)
                    
                    # Reset decorators state
                    current_rate_limit = "—"
                    current_auth = "❌"
                    break

    console.print(table)
    console.print(f"[dim]Prefixed routes generated and registered successfully.[/dim]")
