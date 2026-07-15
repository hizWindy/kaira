"""Info command — show project config and detected models."""

from __future__ import annotations

from rich.panel import Panel
from rich.table import Table

from devflow.config import get_config, find_config_path
from devflow.console import console


def info_command() -> None:
    """Display current DevFlow project configuration and detected models."""
    config = get_config()
    config_path = find_config_path()

    # ── Config panel ──────────────────────────────────────────────────────────
    console.print(
        Panel(
            f"[bold cyan]Config file:[/bold cyan]  {config_path}\n"
            f"[bold cyan]Output dir:[/bold cyan]   {config.output_dir}\n"
            f"[bold cyan]Default tier:[/bold cyan] {config.default_tier}\n"
            f"[bold cyan]AI provider:[/bold cyan]  {config.ai_provider} ({config.ai_model})",
            title="[bold]DevFlow[/bold] — Project Info",
            border_style="cyan",
        )
    )

    # ── Models table ──────────────────────────────────────────────────────────
    if not config.generated_models:
        console.print("[dim]No models generated yet.[/dim]")
        return

    from rich import box
    from devflow.core.theme import Theme

    table = Table(
        title="Generated Models",
        box=box.SIMPLE_HEAD,
        border_style=Theme.PRIMARY,
    )
    table.add_column("Model", style=f"bold {Theme.PRIMARY}", no_wrap=True)
    table.add_column("Fields", style="green")
    table.add_column("Relations", style="yellow")

    for entry in config.generated_models:
        name = entry.get("name", "?")
        fields = entry.get("fields", [])
        relations = entry.get("relations", [])

        fields_str = "\n".join(f"{f['name']}: {f['type']}" for f in fields) or "—"
        rels_str = "\n".join(f"{r['type']} → {r['target']}" for r in relations) or "—"

        table.add_row(name, fields_str, rels_str)

    console.print(table)
