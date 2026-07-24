"""Docs command — AI-powered documentation generation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from devflow.config import get_config, TIER_LAYERS
from devflow.console import console

app = typer.Typer(help="AI-powered API documentation generation.")


def _get_api_client():
    """Return an httpx client configured for the AI provider."""
    try:
        import httpx
        return httpx
    except ImportError:
        console.print("[bold red]✗[/bold red]  httpx is required for AI docs. Run: pip install httpx")
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
        resp = client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
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
        resp = client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def _generate_doc_for_model(model_name: str, fields: list[dict], config) -> str:
    """Generate markdown documentation for one model using the configured AI provider."""
    provider = config.ai_provider.lower()
    api_key_env = config.ai_api_key_env
    api_key = os.getenv(api_key_env, "")

    if not api_key:
        console.print(
            f"[yellow]⚠[/yellow]  No API key found in env var [bold]{api_key_env}[/bold]. "
            f"Set it to enable AI docs."
        )
        return _fallback_doc(model_name, fields)

    fields_desc = "\n".join(f"- `{f['name']}` ({f['type']})" for f in fields)
    prompt = f"""Generate clean Markdown API documentation for a FastAPI resource called "{model_name}".

Fields:
{fields_desc}

Include:
1. Brief description of what the resource represents
2. A table of all fields with Name, Type, Required, Description columns
3. All 5 REST endpoints: POST /, GET /, GET /{{id}}, PUT /{{id}}, DELETE /{{id}}
   - For each: method, path, description, request body (if any), response format
4. Example JSON request and response bodies

Output only Markdown, no explanations."""

    try:
        if provider == "openai":
            return _call_openai(prompt, api_key, config.ai_model)
        elif provider == "anthropic":
            model = config.ai_model if "claude" in config.ai_model else "claude-3-5-sonnet-20241022"
            return _call_anthropic(prompt, api_key, model)
        else:
            console.print(f"[yellow]⚠[/yellow]  Unknown AI provider '{provider}'. Using fallback.")
            return _fallback_doc(model_name, fields)
    except Exception as exc:
        console.print(f"[yellow]⚠[/yellow]  AI API call failed: {exc}. Using fallback doc.")
        return _fallback_doc(model_name, fields)


def _fallback_doc(model_name: str, fields: list[dict]) -> str:
    """Generate basic docs without AI when no API key is available."""
    snake = model_name.lower()
    lines = [
        f"# {model_name} API",
        "",
        f"CRUD endpoints for the `{model_name}` resource.",
        "",
        "## Fields",
        "",
        "| Name | Type | Required |",
        "|------|------|----------|",
    ]
    for f in fields:
        required = "No" if f["type"].startswith("Optional") else "Yes"
        lines.append(f"| `{f['name']}` | `{f['type']}` | {required} |")
    lines += [
        "",
        "## Endpoints",
        "",
        f"| Method | Path | Description |",
        f"|--------|------|-------------|",
        f"| POST   | `/{snake}s/` | Create a new {model_name} |",
        f"| GET    | `/{snake}s/` | List all {model_name}s |",
        f"| GET    | `/{snake}s/{{id}}` | Get {model_name} by ID |",
        f"| PUT    | `/{snake}s/{{id}}` | Update {model_name} by ID |",
        f"| DELETE | `/{snake}s/{{id}}` | Delete {model_name} by ID |",
    ]
    return "\n".join(lines)


@app.command("generate")
def docs_generate(
    model_name: Annotated[
        Optional[str],
        typer.Argument(help="Model name to document. Omit to document all models."),
    ] = None,
) -> None:
    """Generate AI-powered API documentation.

    Writes to docs/api.md (all models) or docs/<ModelName>.md (single model).

    Examples
    --------
    kaira docs generate
    kaira docs generate User
    """
    config = get_config()

    if not config.generated_models:
        console.print("[dim]No tracked models found. Run 'kaira generate model' first.[/dim]")
        raise typer.Exit(0)

    # Filter to requested model(s)
    if model_name:
        models = [m for m in config.generated_models if m.get("name") == model_name]
        if not models:
            console.print(f"[bold red]✗[/bold red]  Model '{model_name}' not tracked. "
                          f"Run 'kaira generate model {model_name}' first.")
            raise typer.Exit(1)
        output_file = Path.cwd() / "docs" / f"{model_name}.md"
    else:
        models = config.generated_models
        output_file = Path.cwd() / "docs" / "api.md"

    output_file.parent.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel(
            f"[bold cyan]Provider:[/bold cyan] {config.ai_provider}\n"
            f"[bold cyan]Model:[/bold cyan]    {config.ai_model}\n"
            f"[bold cyan]Output:[/bold cyan]   {output_file}\n"
            f"[bold cyan]Models:[/bold cyan]   {', '.join(m['name'] for m in models)}",
            title="[bold]Kaira[/bold] — AI Documentation",
            border_style="cyan",
        )
    )

    all_docs: list[str] = ["# API Documentation\n\n*Generated by Kaira*\n"]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Generating docs...", total=len(models))
        for entry in models:
            name = entry.get("name", "?")
            fields = entry.get("fields", [])
            progress.update(task, description=f"[cyan]Documenting {name}...")
            doc = _generate_doc_for_model(name, fields, config)
            all_docs.append(doc)
            progress.advance(task)

    full_doc = "\n\n---\n\n".join(all_docs)
    output_file.write_text(full_doc, encoding="utf-8")
    console.print(f"\n[bold green]✓[/bold green]  Documentation written to [cyan]{output_file}[/cyan]")
