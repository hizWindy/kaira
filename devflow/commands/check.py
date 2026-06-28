"""Check command — show what files would be overwritten."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from devflow.config import get_config, TIER_LAYERS
from devflow.console import console
from devflow.core.generator import resolve_output_path
from devflow.core.detector import file_exists


def check_command() -> None:
    """Show change detection status for all generated models.

    Displays which files exist on disk vs. what DevFlow would generate,
    without actually writing anything.
    """
    config = get_config()

    if not config.generated_models:
        console.print("[dim]No models tracked in .devflow.json yet. Run 'devflow generate model' first.[/dim]")
        raise typer.Exit(0)

    table = Table(
        title="Change Detection Report",
        border_style="cyan",
        show_lines=True,
    )
    table.add_column("Model", style="bold cyan", no_wrap=True)
    table.add_column("Layer", style="bold")
    table.add_column("File", style="dim")
    table.add_column("Status", justify="center")

    tier = config.default_tier
    layers = TIER_LAYERS.get(tier, TIER_LAYERS["full"])

    for entry in config.generated_models:
        model_name = entry.get("name", "?")
        for layer in layers:
            out_path = resolve_output_path(layer, model_name, config, Path.cwd())
            exists = file_exists(out_path)
            status = (
                "[yellow]⚠ exists — would overwrite[/yellow]"
                if exists
                else "[green]✓ new file[/green]"
            )
            table.add_row(
                model_name,
                layer,
                str(out_path.relative_to(Path.cwd())),
                status,
            )

    console.print(table)
    console.print("[dim]Run 'devflow generate model <ModelName> --force' to overwrite, or omit --force to be prompted.[/dim]")
