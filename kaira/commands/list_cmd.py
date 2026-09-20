"""List command group — list models and routes."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from kaira.config import get_config
from kaira.console import console

app = typer.Typer(help="List generated resources.")


@app.command("models")
def list_models() -> None:
    """List all generated model files in the models directory."""
    config = get_config()
    models_dir = Path.cwd() / config.models_dir

    if not models_dir.exists():
        console.print(
            f"[yellow]⚠[/yellow]  Models directory not found: [dim]{models_dir}[/dim]"
        )
        raise typer.Exit(0)

    model_files = sorted(
        f for f in models_dir.iterdir() if f.suffix == ".py" and f.name != "__init__.py"
    )

    if not model_files:
        console.print("[dim]No model files found.[/dim]")
        return

    from rich import box
    from kaira.core.theme import Theme

    table = Table(
        title=f"Models in [cyan]{models_dir}[/cyan]",
        box=box.SIMPLE_HEAD,
        border_style=Theme.PRIMARY,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style=f"bold {Theme.PRIMARY}")
    table.add_column("Size", style=Theme.MUTED, justify="right")

    for i, f in enumerate(model_files, 1):
        size = f"{f.stat().st_size:,} B"
        table.add_row(str(i), f.name, size)

    console.print(table)
    console.print(f"[dim]{len(model_files)} model(s) found.[/dim]")


@app.command("routes")
def list_routes() -> None:
    """List all generated router endpoints with prefixed paths, methods, auth, and rate limits."""
    config = get_config()
    routers_dir = Path.cwd() / config.routers_dir

    if not routers_dir.exists():
        console.print(
            f"[yellow]⚠[/yellow]  Routers directory not found: [dim]{routers_dir}[/dim]"
        )
        raise typer.Exit(0)

    router_files = sorted(
        f
        for f in routers_dir.iterdir()
        if f.suffix == ".py" and f.name != "__init__.py"
    )

    if not router_files:
        console.print("[dim]No router files found.[/dim]")
        return

    api_version = getattr(config, "api_version", "v1")
    api_prefix = f"/api/{api_version}"

    from rich import box
    from kaira.core.theme import Theme

    table = Table(
        title="Khaira — Registered API Routes",
        box=box.SIMPLE_HEAD,
        border_style=Theme.PRIMARY,
    )
    table.add_column("Route", style=f"bold {Theme.PRIMARY}")
    table.add_column("Method", width=10)
    table.add_column("Security", width=12)
    table.add_column("Rate Limit", style=Theme.MUTED)

    http_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

    for f in router_files:
        content = f.read_text(encoding="utf-8")

        # 1. Parse Router Prefix
        import re

        prefix_match = re.search(r"prefix\s*=\s*[\"']([^\"']+)[\"']", content)
        router_prefix = prefix_match.group(1) if prefix_match else ""
        if not router_prefix.startswith("/"):
            router_prefix = "/" + router_prefix

        # 2. Find all route decorators — supports both single-line and multi-line forms:
        #    Single-line: @router.get("/path", ...)
        #    Multi-line:  @router.get(\n    "/path",\n    ...)
        lines = content.split("\n")
        current_rate_limit = "—"

        for idx, line in enumerate(lines):
            line_str = line.strip()

            # Match Rate limit decorator
            limit_match = re.match(r"@limiter\.limit\(([^)]+)\)", line_str)
            if limit_match:
                limit_val = limit_match.group(1).strip("\"'")
                if "RATE_LIMIT_GET" in limit_val:
                    current_rate_limit = "60/min"
                elif "RATE_LIMIT_WRITE" in limit_val:
                    current_rate_limit = "20/min"
                else:
                    current_rate_limit = limit_val.replace("/minute", "/min")
                continue

            # Match HTTP method decorators in both single-line and multi-line form
            for method in http_methods:
                method_lower = method.lower()

                # Single-line: @router.get("/path", ...)
                single_pat = rf"@router\.{method_lower}\(\s*[\"']([^\"']*)[\"']"
                route_match = re.match(single_pat, line_str)

                # Multi-line: @router.get(  with path on next non-empty line
                if not route_match and re.match(
                    rf"@router\.{method_lower}\(\s*$", line_str
                ):
                    for offset in range(1, 5):
                        if idx + offset < len(lines):
                            next_stripped = lines[idx + offset].strip()
                            path_match = re.match(
                                r"""[\"']([^\"']*)[\"']""", next_stripped
                            )
                            if path_match:
                                # Fake a match object by storing the group
                                sub_path = path_match.group(1)
                                route_match = True  # sentinel
                                break
                    else:
                        sub_path = ""
                elif route_match:
                    sub_path = route_match.group(1)

                if route_match:
                    if sub_path == "/":
                        sub_path = ""
                    elif sub_path and not sub_path.startswith("/"):
                        sub_path = "/" + sub_path

                    full_route = f"{api_prefix}{router_prefix}{sub_path}"
                    full_route = re.sub(r"/+", "/", full_route)

                    # Look ahead for auth guard in the function signature
                    has_auth = False
                    for offset in range(1, 15):
                        if idx + offset < len(lines):
                            if "def " in lines[idx + offset]:
                                sig_lines = []
                                for sig_offset in range(0, 10):
                                    if idx + offset + sig_offset < len(lines):
                                        sig_lines.append(
                                            lines[idx + offset + sig_offset]
                                        )
                                        if "):" in lines[idx + offset + sig_offset]:
                                            break
                                sig_str = "".join(sig_lines)
                                if (
                                    "get_current_user" in sig_str
                                    or "validate_api_key" in sig_str
                                ):
                                    has_auth = True
                                break

                    auth_str = (
                        "[bold green]🔒 SECURE[/bold green]"
                        if has_auth
                        else "[dim red]🔓 PUBLIC[/dim red]"
                    )

                    method_colors = {
                        "GET": "green",
                        "POST": "blue",
                        "PUT": "yellow",
                        "PATCH": "magenta",
                        "DELETE": "red",
                    }
                    mcolor = method_colors.get(method, "white")
                    method_str = f"[bold {mcolor}]{method:<6}[/bold {mcolor}]"

                    table.add_row(full_route, method_str, auth_str, current_rate_limit)
                    current_rate_limit = "—"
                    break

    console.print(table)
    console.print("[dim]Prefixed routes generated and registered successfully.[/dim]")
