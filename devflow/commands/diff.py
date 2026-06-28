"""Diff command — show diff between existing and generated files."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from devflow.config import get_config, TIER_LAYERS
from devflow.console import console
from devflow.core.parser import parse_fields, validate_model_name, FieldDef
from devflow.core.generator import generate_layer, resolve_output_path
from devflow.core.detector import show_diff, file_exists


def diff_command(
    model_name: str,
    fields: Optional[str] = None,
    layer: Optional[str] = None,
) -> None:
    """Show a unified diff between the existing file(s) and freshly generated content.

    Parameters
    ----------
    model_name:
        PascalCase model name.
    fields:
        Optional field overrides for regeneration.
    layer:
        If given, only diff this specific layer. Otherwise diff all layers.
    """
    try:
        validate_model_name(model_name)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    config = get_config()

    # Load fields from config or CLI override
    if fields:
        try:
            parsed_fields = parse_fields(fields)
        except ValueError as exc:
            console.print(f"[bold red]✗[/bold red]  {exc}")
            raise typer.Exit(1)
    else:
        # Try to load stored fields from .devflow.json
        parsed_fields = []
        for entry in config.generated_models:
            if entry.get("name") == model_name:
                raw_list = entry.get("fields", [])
                try:
                    fields_str = ", ".join(f"{f['name']}:{f['type']}" for f in raw_list)
                    parsed_fields = parse_fields(fields_str)
                except (ValueError, KeyError):
                    pass
                break

    tier = config.default_tier
    layers_to_diff = [layer] if layer else TIER_LAYERS.get(tier, TIER_LAYERS["full"])

    found_any = False
    for lyr in layers_to_diff:
        out_path = resolve_output_path(lyr, model_name, config, Path.cwd())
        if not file_exists(out_path):
            console.print(f"[dim]→ {lyr}: file does not exist yet: {out_path}[/dim]")
            continue

        found_any = True
        new_content = generate_layer(lyr, model_name, parsed_fields, [], config)
        show_diff(out_path, new_content)

    if not found_any:
        console.print(
            f"[yellow]⚠[/yellow]  No existing files found for [bold]{model_name}[/bold]. "
            f"Nothing to diff."
        )
