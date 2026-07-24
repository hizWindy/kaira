"""Diff command — show Rich-highlighted diff between existing and generated files.

Annotates field changes inline and offers an interactive [o]verwrite / [s]kip /
[v]iew full file prompt after displaying each diff.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.text import Text

from devflow.config import get_config, TIER_LAYERS
from devflow.console import console
from devflow.core.parser import parse_fields, validate_model_name
from devflow.core.generator import generate_layer, resolve_output_path
from devflow.core.detector import file_exists


# ---------------------------------------------------------------------------
# Annotation helpers
# ---------------------------------------------------------------------------


def _annotate_diff_line(line: str) -> str:
    """Add inline annotations to a diff line where we can detect field changes.

    Args:
        line: A single line from the unified diff output.

    Returns:
        Line with appended annotation comment when relevant.
    """
    if not line.startswith(("+", "-")):
        return line

    # Detect field length changes (e.g. max_length= values)
    if re.search(r"max_length\s*=\s*\d+", line):
        return line.rstrip() + "  # ← length changed"

    # Detect new field declarations in SQLAlchemy / Pydantic
    if re.search(
        r":\s*(str|int|float|bool|datetime|Optional)\b", line
    ) and line.startswith("+"):
        return line.rstrip() + "  # ← new field"

    # Detect removed field declarations
    if re.search(
        r":\s*(str|int|float|bool|datetime|Optional)\b", line
    ) and line.startswith("-"):
        return line.rstrip() + "  # ← removed field"

    return line


def _build_annotated_diff(existing: str, new: str, filename: str) -> str:
    """Build an annotated unified diff string.

    Args:
        existing: Existing file content.
        new: Newly generated content.
        filename: Filename shown in diff headers.

    Returns:
        Annotated unified diff string.
    """
    existing_lines = existing.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    raw = difflib.unified_diff(
        existing_lines,
        new_lines,
        fromfile=f"existing/{filename}",
        tofile=f"generated/{filename}",
        lineterm="",
    )
    annotated = [_annotate_diff_line(line) for line in raw]
    return "\n".join(annotated)


# ---------------------------------------------------------------------------
# Public command function
# ---------------------------------------------------------------------------


def diff_command(
    model_name: str,
    fields: Optional[str] = None,
    layer: Optional[str] = None,
) -> None:
    """Show a Rich-highlighted diff between the existing file(s) and freshly generated content.

    Displays inline annotations for changed/new/removed fields. After each diff,
    prompts: [o] Overwrite  [s] Skip  [v] View full file.

    Args:
        model_name: PascalCase model name.
        fields: Optional field overrides for regeneration.
        layer: If given, only diff this specific layer. Otherwise diff all layers.
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

        try:
            existing_content = out_path.read_text(encoding="utf-8")
        except OSError:
            existing_content = ""

        diff_text = _build_annotated_diff(existing_content, new_content, out_path.name)

        if not diff_text.strip():
            console.print(
                Panel(
                    "[dim]No changes detected — generated output is identical.[/dim]",
                    title=f"[bold cyan]Diff: {out_path.name}[/bold cyan]",
                    border_style="cyan",
                )
            )
            continue

        # Display Rich syntax-highlighted diff
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
        console.print(
            Panel(
                syntax,
                title=f"[bold cyan]Diff: {out_path.name}[/bold cyan]",
                border_style="cyan",
            )
        )

        # Interactive prompt after each diff
        try:
            import questionary
            choice = questionary.select(
                f"Action for diff {out_path.name}:",
                choices=[
                    {"name": "overwrite", "value": "o"},
                    {"name": "skip", "value": "s"},
                    {"name": "view full file", "value": "v"},
                ],
                default="s",
            ).ask()
        except Exception:
            console.print(
                Text.from_markup(
                    "\n  [bold cyan]o[/bold cyan] Overwrite  "
                    "[bold blue]s[/bold blue] Skip  "
                    "[bold magenta]v[/bold magenta] View full file\n"
                )
            )
            choice = Prompt.ask(
                "[bold]Action[/bold]",
                choices=["o", "s", "v"],
                default="s",
            )

        if choice == "o":
            out_path.write_text(new_content, encoding="utf-8")
            console.print(f"  [green]✅ Overwritten:[/green] [cyan]{out_path}[/cyan]")
        elif choice == "v":
            console.print(
                Panel(
                    Syntax(new_content, "python", theme="monokai", line_numbers=True),
                    title=f"[bold magenta]Full File: {out_path.name}[/bold magenta]",
                    border_style="magenta",
                )
            )
        else:
            console.print(f"  [dim]→ Skipped: {out_path}[/dim]")

    if not found_any:
        console.print(
            f"[yellow]⚠[/yellow]  No existing files found for [bold]{model_name}[/bold]. "
            f"Nothing to diff."
        )
