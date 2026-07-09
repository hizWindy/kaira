"""DevFlow api command group — API inspection, testing, and client generation.

Connects to the local dev server (http://127.0.0.1:8000). If the server is down,
prints a clear start command. Never echoes or stores auth tokens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from devflow.console import console

app = typer.Typer(help="API inspection, testing, and client generation.")

_BASE_URL = "http://127.0.0.1:8000"
_SERVER_DOWN_MSG = (
    "⏸️ Server not running.\n"
    "Start it with: [bold cyan]uvicorn main:app --reload[/bold cyan]"
)


def _fetch_openapi(base_url: str = _BASE_URL) -> Optional[dict]:
    """Fetch and return the OpenAPI spec from the local dev server.

    Args:
        base_url: Base URL of the running FastAPI app.

    Returns:
        Parsed OpenAPI spec dict, or None if server is unreachable.
    """
    try:
        import httpx

        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{base_url}/openapi.json")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("export")
def api_export(
    fmt: Annotated[
        str,
        typer.Option("--format", help="Export format: json | yaml"),
    ] = "json",
) -> None:
    """Export the OpenAPI spec from the local dev server.

    Args:
        fmt: Output format — 'json' or 'yaml'.
    """
    spec = _fetch_openapi()
    if spec is None:
        console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        raise typer.Exit(1)

    if fmt == "json":
        out = Path("openapi.json")
        out.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        console.print(f"[green]✅ OpenAPI spec exported to [cyan]{out}[/cyan][/green]")
    elif fmt == "yaml":
        try:
            import yaml  # type: ignore[import]
        except ImportError:
            console.print("[red]❌ PyYAML not installed. Run: pip install pyyaml[/red]")
            raise typer.Exit(1)
        out = Path("openapi.yaml")
        out.write_text(yaml.dump(spec, sort_keys=False), encoding="utf-8")
        console.print(f"[green]✅ OpenAPI spec exported to [cyan]{out}[/cyan][/green]")
    else:
        console.print(
            f"[red]❌ Unknown format '{fmt}'. Use --format json or --format yaml[/red]"
        )
        raise typer.Exit(1)


@app.command("validate")
def api_validate() -> None:
    """Validate the OpenAPI spec structure from the local dev server."""
    spec = _fetch_openapi()
    if spec is None:
        console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        raise typer.Exit(1)

    errors: list[str] = []
    if "openapi" not in spec:
        errors.append("Missing 'openapi' version field")
    if "info" not in spec:
        errors.append("Missing 'info' block")
    if "paths" not in spec:
        errors.append("Missing 'paths' block")

    if errors:
        console.print(
            Panel(
                "\n".join(f"[red]❌ {e}[/red]" for e in errors),
                title="Validation Errors",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    route_count = sum(len(methods) for methods in spec["paths"].values())
    console.print(
        Panel(
            f"[green]✅ OpenAPI spec valid — {len(spec['paths'])} paths, {route_count} operations[/green]",
            border_style="green",
        )
    )


@app.command("list")
def api_list() -> None:
    """List all routes registered in the local dev server."""
    spec = _fetch_openapi()
    if spec is None:
        console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        raise typer.Exit(1)

    table = Table(title="⚡ API Routes", border_style="cyan")
    table.add_column("Method", style="bold")
    table.add_column("Path", style="cyan")
    table.add_column("Summary")

    for path, methods in sorted(spec.get("paths", {}).items()):
        for method, op in methods.items():
            table.add_row(
                method.upper(),
                path,
                op.get("summary", "[dim]—[/dim]"),
            )
    console.print(table)


@app.command("test")
def api_test(
    method: Annotated[
        str, typer.Argument(help="HTTP method: GET, POST, PUT, DELETE, PATCH")
    ],
    route: Annotated[str, typer.Argument(help="Route path, e.g. /users")],
    body: Annotated[
        Optional[str], typer.Option("--body", help="JSON request body")
    ] = None,
) -> None:
    """Send a test request to the local dev server.

    Never echoes or stores auth tokens in output.

    Args:
        method: HTTP method.
        route: Route path.
        body: Optional JSON body string.
    """
    try:
        import httpx
    except ImportError:
        console.print("[red]❌ httpx not installed. Run: pip install httpx[/red]")
        raise typer.Exit(1)

    url = f"{_BASE_URL}{route}"
    parsed_body = None
    if body:
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError as exc:
            console.print(f"[red]❌ Invalid JSON body: {exc}[/red]")
            raise typer.Exit(1)

    console.print(f"[cyan]{method.upper()} {url}[/cyan]")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.request(method.upper(), url, json=parsed_body)
        console.print(f"[bold]Status:[/bold] {resp.status_code}")
        try:
            response_body = resp.json()
            console.print(
                Panel(
                    Syntax(
                        json.dumps(response_body, indent=2), "json", theme="monokai"
                    ),
                    title="Response",
                    border_style="green" if resp.status_code < 400 else "red",
                )
            )
        except Exception:
            console.print(resp.text[:2000])
    except httpx.ConnectError:
        console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        raise typer.Exit(1)


@app.command("postman")
def api_postman() -> None:
    """Generate a Postman collection JSON from the local OpenAPI spec."""
    spec = _fetch_openapi()
    if spec is None:
        console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        raise typer.Exit(1)

    title = spec.get("info", {}).get("title", "DevFlow API")
    collection: dict = {
        "info": {
            "name": title,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
    }

    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            collection["item"].append(
                {
                    "name": op.get("summary", f"{method.upper()} {path}"),
                    "request": {
                        "method": method.upper(),
                        "url": {
                            "raw": f"{{{{base_url}}}}{path}",
                            "host": ["{{base_url}}"],
                            "path": path.strip("/").split("/"),
                        },
                        "header": [],
                    },
                }
            )

    out = Path("postman_collection.json")
    out.write_text(json.dumps(collection, indent=2), encoding="utf-8")
    console.print(
        f"[green]✅ Postman collection exported to [cyan]{out}[/cyan][/green]"
    )


@app.command("client")
def api_client(
    lang: Annotated[
        str,
        typer.Option("--lang", help="Target language: typescript | javascript"),
    ] = "typescript",
) -> None:
    """Generate a typed API client from the local OpenAPI spec.

    Args:
        lang: Target language for the generated client.
    """
    spec = _fetch_openapi()
    if spec is None:
        console.print(Panel(_SERVER_DOWN_MSG, border_style="yellow"))
        raise typer.Exit(1)

    valid = {"typescript", "javascript"}
    if lang not in valid:
        console.print(
            f"[red]❌ Unknown language '{lang}'. Use: {', '.join(valid)}[/red]"
        )
        raise typer.Exit(1)

    ext = "ts" if lang == "typescript" else "js"
    out_lines: list[str] = [
        f"// Generated by DevFlow — {lang} API client",
        f"// Source: {_BASE_URL}/openapi.json",
        "",
        f"const BASE_URL = '{_BASE_URL}';",
        "",
    ]

    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            func_name = (
                method.lower()
                + "_"
                + path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
            )
            summary = op.get("summary", "")
            params = (
                "params?: Record<string, unknown>" if lang == "typescript" else "params"
            )
            return_type = ": Promise<unknown>" if lang == "typescript" else ""
            out_lines += [
                f"/** {summary} */",
                f"export async function {func_name}({params}){return_type} {{",
                f"  const response = await fetch(`${{BASE_URL}}{path}`, {{",
                f"    method: '{method.upper()}',",
                "    headers: { 'Content-Type': 'application/json' },",
                "    ...(params && { body: JSON.stringify(params) }),",
                "  });",
                "  return response.json();",
                "}",
                "",
            ]

    out_file = Path(f"api_client.{ext}")
    out_file.write_text("\n".join(out_lines), encoding="utf-8")
    console.print(
        f"[green]✅ {lang.capitalize()} client generated: [cyan]{out_file}[/cyan][/green]"
    )
