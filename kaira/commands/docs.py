"""Docs command — AI-powered documentation generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from kaira.config import get_config
from kaira.console import console
from kaira.core.route_discovery import RouteGroup, discover_routes

app = typer.Typer(help="AI-powered API documentation generation.")

# How each group is labelled in the generated Markdown.
_KIND_LABEL = {
    "model": "generated CRUD",
    "system": "Kaira scaffolding",
    "custom": "custom router",
}


def _get_api_client():
    """Return an httpx client configured for the AI provider."""
    try:
        import httpx

        return httpx
    except ImportError:
        console.print(
            "[bold red]✗[/bold red]  httpx is required for AI docs. Run: pip install httpx"
        )
        raise typer.Exit(1)


def _call_openai(prompt: str, api_key: str, model: str) -> str:
    """Call OpenAI chat completions API and return the response text."""
    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a technical writer generating concise, accurate API documentation. "
                    "Output clean Markdown with no extra commentary."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1500,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions", json=payload, headers=headers
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, api_key: str, model: str) -> str:
    """Call Anthropic messages API and return the response text."""
    import httpx

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}],
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages", json=payload, headers=headers
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def _endpoint_table(group: RouteGroup) -> list[str]:
    """Render the group's real endpoints as a Markdown table."""
    lines = [
        "| Method | Path | Auth | Description |",
        "|--------|------|------|-------------|",
    ]
    for endpoint in group.endpoints:
        detail = endpoint.summary or endpoint.description or "—"
        detail = detail.replace("|", "\\|").strip()
        auth = "🔒" if endpoint.auth_required else "—"
        lines.append(f"| {endpoint.method} | `{endpoint.path}` | {auth} | {detail} |")
    return lines


def _field_table(fields: list[dict]) -> list[str]:
    """Render a model's fields as a Markdown table."""
    lines = ["| Name | Type | Required |", "|------|------|----------|"]
    for f in fields:
        required = "No" if str(f.get("type", "")).startswith("Optional") else "Yes"
        lines.append(f"| `{f.get('name')}` | `{f.get('type')}` | {required} |")
    return lines


def _group_heading(group: RouteGroup) -> str:
    """``## Analytics — custom router (routers/analytics_router.py)``."""
    label = _KIND_LABEL.get(group.kind, group.kind)
    source = f" · `{group.source_file}`" if group.source_file else ""
    return f"## {group.name} — {label}{source}"


def _fallback_doc(group: RouteGroup, fields: list[dict]) -> str:
    """Build docs from the discovered routes, with no AI involved.

    Endpoints come from the project itself rather than an assumed CRUD shape,
    so a hand-written router documents exactly the routes it declares.
    """
    lines = [_group_heading(group), ""]
    if fields:
        lines += ["### Fields", ""] + _field_table(fields) + [""]
    lines += ["### Endpoints", ""] + _endpoint_table(group)
    return "\n".join(lines)


def _generate_doc_for_group(group: RouteGroup, fields: list[dict], config) -> str:
    """Document one route group using the configured AI provider.

    Falls back to the deterministic renderer when no API key is configured or
    the call fails — the discovered routes are correct either way, so docs are
    never blocked on the AI being reachable.
    """
    provider = config.ai_provider.lower()
    api_key_env = config.ai_api_key_env
    api_key = os.getenv(api_key_env, "")

    if not api_key:
        return _fallback_doc(group, fields)

    routes_desc = "\n".join(
        f"- {e.method} {e.path}"
        + (f" — {e.summary}" if e.summary else "")
        + (" (requires authentication)" if e.auth_required else "")
        + (f" [request: {e.request_model}]" if e.request_model else "")
        + (f" [response: {e.response_model}]" if e.response_model else "")
        for e in group.endpoints
    )
    fields_desc = (
        "\n".join(f"- `{f['name']}` ({f['type']})" for f in fields)
        if fields
        else "(no tracked model — this is a hand-written router)"
    )

    prompt = f"""Generate clean Markdown API documentation for the "{group.name}" section of a FastAPI service.

These are the ACTUAL endpoints, read from the running application. Document
exactly these — do not invent, rename, or omit any, and do not assume a
standard CRUD set:
{routes_desc}

Model fields, if this section is backed by one:
{fields_desc}

Include:
1. A one-paragraph description of what this section is for, inferred from the routes
2. A field table (Name, Type, Required, Description) only if fields are listed above
3. A table of every endpoint: Method, Path, Auth required, Description
4. Example JSON request and response bodies for the most important endpoints

Start at heading level 2 (`##`). Output only Markdown, no commentary."""

    try:
        if provider == "openai":
            return _call_openai(prompt, api_key, config.ai_model)
        if provider == "anthropic":
            model = (
                config.ai_model
                if "claude" in config.ai_model
                else "claude-3-5-sonnet-20241022"
            )
            return _call_anthropic(prompt, api_key, model)
        console.print(
            f"[yellow]⚠[/yellow]  Unknown AI provider '{provider}'. Using fallback."
        )
        return _fallback_doc(group, fields)
    except Exception as exc:
        console.print(
            f"[yellow]⚠[/yellow]  AI API call failed: {exc}. Using fallback doc."
        )
        return _fallback_doc(group, fields)


def _contents_index(groups: list[RouteGroup]) -> list[str]:
    """A table of contents, so a custom router is visible at a glance."""
    lines = ["## Contents", ""]
    for group in groups:
        anchor = group.name.lower().replace(" ", "-")
        label = _KIND_LABEL.get(group.kind, group.kind)
        count = len(group.endpoints)
        plural = "endpoint" if count == 1 else "endpoints"
        lines.append(f"- [{group.name}](#{anchor}) — {count} {plural} ({label})")
    return lines


@app.command("generate")
def docs_generate(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Section to document (model or router tag). Omit for all."),
    ] = None,
    source_only: Annotated[
        bool,
        typer.Option(
            "--source",
            help="Read routes from source instead of importing the app.",
        ),
    ] = False,
    custom_only: Annotated[
        bool,
        typer.Option("--custom", help="Document only hand-written routers."),
    ] = False,
) -> None:
    """Generate API documentation from the routes the project actually exposes.

    Every mounted router is documented — generated CRUD, auth, and any custom
    router you wrote yourself. Routes are read from the live OpenAPI schema
    when the app can be imported, and parsed from source otherwise.

    Writes to docs/api.md, or docs/<Name>.md for a single section.

    Examples
    --------
    kaira docs generate
    kaira docs generate Analytics
    kaira docs generate --custom
    kaira docs generate --source
    """
    config = get_config()
    base = Path.cwd()
    model_names = {m.get("name") for m in config.generated_models if m.get("name")}
    fields_by_model = {
        m.get("name"): m.get("fields", []) for m in config.generated_models
    }

    with console.status("[cyan]Discovering routes..."):
        groups, strategy = discover_routes(
            base,
            model_names,
            prefer_live=not source_only,
            api_prefix=f"/api/{getattr(config, 'api_version', 'v1')}",
        )

    if not groups:
        console.print(
            "[dim]No routes found. Run 'kaira generate model' or add a router "
            "under routers/ first.[/dim]"
        )
        raise typer.Exit(0)

    if custom_only:
        groups = [g for g in groups if g.is_custom]
        if not groups:
            console.print(
                "[dim]No custom routers found — every route is generated.[/dim]"
            )
            raise typer.Exit(0)

    if target:
        matched = [g for g in groups if g.name.lower() == target.lower()]
        if not matched:
            available = ", ".join(g.name for g in groups)
            console.print(
                f"[bold red]✗[/bold red]  No route group named '{target}'. "
                f"Available: {available}"
            )
            raise typer.Exit(1)
        groups = matched
        output_file = base / "docs" / f"{matched[0].name}.md"
    else:
        output_file = base / "docs" / "api.md"

    output_file.parent.mkdir(parents=True, exist_ok=True)

    total = sum(len(g.endpoints) for g in groups)
    custom_count = sum(1 for g in groups if g.is_custom)
    if strategy == "openapi":
        how = "live OpenAPI schema"
    elif source_only:
        how = "source scan (--source)"
    else:
        # Falling back silently would hide that the docs may be less precise.
        how = "source scan — the app could not be imported"
    console.print(
        Panel(
            f"[bold cyan]Provider:[/bold cyan]  {config.ai_provider}\n"
            f"[bold cyan]Model:[/bold cyan]     {config.ai_model}\n"
            f"[bold cyan]Detected:[/bold cyan]  {how}\n"
            f"[bold cyan]Sections:[/bold cyan]  {len(groups)} "
            f"({custom_count} custom) · {total} endpoints\n"
            f"[bold cyan]Output:[/bold cyan]    {output_file}",
            title="[bold]Kaira[/bold] — API Documentation",
            border_style="cyan",
        )
    )

    header = [
        "# API Documentation",
        "",
        f"*Generated by Kaira — {total} endpoints across {len(groups)} sections, "
        f"detected via {how}.*",
        "",
    ]
    all_docs: list[str] = ["\n".join(header + _contents_index(groups))]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Generating docs...", total=len(groups))
        for group in groups:
            progress.update(task, description=f"[cyan]Documenting {group.name}...")
            all_docs.append(
                _generate_doc_for_group(
                    group, fields_by_model.get(group.name, []), config
                )
            )
            progress.advance(task)

    output_file.write_text("\n\n---\n\n".join(all_docs), encoding="utf-8")
    console.print(
        f"\n[bold green]✓[/bold green]  Documentation written to [cyan]{output_file}[/cyan]"
    )
    if custom_count:
        names = ", ".join(g.name for g in groups if g.is_custom)
        console.print(f"[dim]Included custom router(s): {names}[/dim]")
