"""Check command — show what files would be overwritten."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from kaira.config import TIER_LAYERS, get_config
from kaira.console import console
from kaira.core.detector import file_exists
from kaira.core.generator import resolve_output_path


def check_command() -> None:
    """Show change detection status for all generated models.

    Displays which files exist on disk vs. what Kaira would generate,
    without actually writing anything.
    """
    config = get_config()

    if not config.generated_models:
        console.print(
            "[dim]No models tracked in .kaira.json yet. Run 'kaira generate model' first.[/dim]"
        )
        raise typer.Exit(0)

    from rich import box

    from kaira.core.theme import Theme

    table = Table(
        title="Change Detection Report",
        box=box.SIMPLE_HEAD,
        border_style=Theme.PRIMARY,
    )
    table.add_column("Model", style=f"bold {Theme.PRIMARY}", no_wrap=True)
    table.add_column("Layer", style="bold")
    table.add_column("File", style=Theme.MUTED)
    table.add_column("Status", justify="left")

    tier = config.default_tier
    layers = TIER_LAYERS.get(tier, TIER_LAYERS["full"])

    for entry in config.generated_models:
        model_name = entry.get("name", "?")
        for layer in layers:
            out_path = resolve_output_path(layer, model_name, config, Path.cwd())
            exists = file_exists(out_path)
            status = (
                "[bold yellow]⚠ exists — would overwrite[/bold yellow]"
                if exists
                else "[bold green]✓ new file[/bold green]"
            )
            table.add_row(
                model_name,
                layer,
                str(out_path.relative_to(Path.cwd())),
                status,
            )

    console.print(table)
    console.print(
        "[dim]Run 'kaira generate model <ModelName> --force' to overwrite, or omit --force to be prompted.[/dim]"
    )
