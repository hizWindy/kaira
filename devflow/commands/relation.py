"""Relation command — add relationships between models."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel

from devflow.config import get_config
from devflow.console import console
from devflow.core.parser import validate_model_name, camel_to_snake, parse_relation
from devflow.core.generator import resolve_output_path
from devflow.core.detector import file_exists

app = typer.Typer(help="Add relationships between models.")


def _append_relation_block(model_file: Path, relation_block: str) -> None:
    """Append a relationship block to an existing model file."""
    content = model_file.read_text(encoding="utf-8")

    # Insert before the __repr__ method, or at the end of the class
    marker = "    def __repr__"
    if marker in content:
        idx = content.index(marker)
        new_content = content[:idx] + relation_block + "\n" + content[idx:]
    else:
        new_content = content.rstrip() + "\n\n" + relation_block + "\n"

    model_file.write_text(new_content, encoding="utf-8")


def _build_relation_block(
    model_name: str,
    relation_type: str,
    target: str,
    cascade: Optional[str],
) -> str:
    """Build a relationship code block to append to the source model."""
    snake_self = camel_to_snake(model_name)
    snake_target = camel_to_snake(target)

    lines: list[str] = []

    if relation_type == "one-to-many":
        lines.append(f"    # ── One-to-Many: {model_name} → {target} ─────────────────────────")
        lines.append(f"    {snake_target}s: Mapped[list[\"{target}\"]] = relationship(")
        lines.append(f'        "{target}",')
        lines.append(f'        back_populates="{snake_self}",')
        if cascade:
            lines.append(f'        cascade="{cascade}",')
        lines.append("    )")

    elif relation_type == "many-to-one":
        lines.append(f"    # ── Many-to-One: {model_name} → {target} ─────────────────────────")
        lines.append(f"    {snake_target}_id: Mapped[int] = mapped_column(Integer, ForeignKey(\"{snake_target}s.id\"), nullable=True)")
        lines.append(f"    {snake_target}: Mapped[\"{target}\"] = relationship(")
        lines.append(f'        "{target}",')
        lines.append(f'        back_populates="{snake_self}s",')
        lines.append("    )")

    elif relation_type == "many-to-many":
        assoc_table = f"{snake_self}_{snake_target}_association"
        lines.append(f"    # ── Many-to-Many: {model_name} ↔ {target} ─────────────────────────")
        lines.append(f"    {snake_target}s: Mapped[list[\"{target}\"]] = relationship(")
        lines.append(f'        "{target}",')
        lines.append(f"        secondary={assoc_table},")
        lines.append(f'        back_populates="{snake_self}s",')
        lines.append("    )")

    return "\n".join(lines) + "\n"


@app.command("relation")
def add_relation(
    model_a: Annotated[str, typer.Argument(help="Source model (PascalCase)")],
    has_many: Annotated[Optional[str], typer.Option("--has-many", help="Target model for one-to-many")] = None,
    has_one: Annotated[Optional[str], typer.Option("--has-one", help="Target model for many-to-one")] = None,
    many_to_many: Annotated[Optional[str], typer.Option("--many-to-many", help="Target model for many-to-many")] = None,
    cascade: Annotated[Optional[str], typer.Option("--cascade", help='Cascade option e.g. "all, delete-orphan"')] = None,
) -> None:
    """Add a relationship to MODEL_A's model file.

    Examples
    --------
    devflow add relation Post --has-many Comment --cascade "all, delete-orphan"
    devflow add relation Post --has-one User
    devflow add relation Post --many-to-many Tag
    """
    # Validate model A
    try:
        validate_model_name(model_a)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    # Determine relation type and target
    if has_many:
        relation_type = "one-to-many"
        target = has_many
    elif has_one:
        relation_type = "many-to-one"
        target = has_one
    elif many_to_many:
        relation_type = "many-to-many"
        target = many_to_many
    else:
        console.print("[bold red]✗[/bold red]  Specify one of --has-many, --has-one, or --many-to-many")
        raise typer.Exit(1)

    try:
        validate_model_name(target)
        parse_relation(relation_type, target, cascade)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    # Find the model file
    config = get_config()
    model_file = resolve_output_path("model", model_a, config, Path.cwd())

    if not file_exists(model_file):
        console.print(
            f"[bold red]✗[/bold red]  Model file not found: [dim]{model_file}[/dim]\n"
            f"[dim]Run 'devflow generate model {model_a}' first.[/dim]"
        )
        raise typer.Exit(1)

    rel_block = _build_relation_block(model_a, relation_type, target, cascade)

    console.print(
        Panel(
            f"[bold cyan]Model:[/bold cyan]    {model_a}\n"
            f"[bold cyan]Relation:[/bold cyan] {relation_type}\n"
            f"[bold cyan]Target:[/bold cyan]   {target}"
            + (f"\n[bold cyan]Cascade:[/bold cyan]  {cascade}" if cascade else ""),
            title="[bold]DevFlow[/bold] — Adding Relationship",
            border_style="cyan",
        )
    )

    _append_relation_block(model_file, rel_block)
    console.print(f"[bold green]✓[/bold green]  Relationship added to [cyan]{model_file}[/cyan]")

    if relation_type == "many-to-many":
        # Remind user to create association table
        snake_a = camel_to_snake(model_a)
        snake_b = camel_to_snake(target)
        console.print(
            f"[yellow]⚠[/yellow]  For many-to-many, create an association table: "
            f"[dim]{snake_a}_{snake_b}_association.py[/dim]\n"
            f"[dim]   Run: devflow generate model {model_a} --fields ... to regenerate with the relation built-in.[/dim]"
        )
