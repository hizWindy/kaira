"""Generate command group — scaffold 5-layer pipelines."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from kaira.console import console
from kaira.commands.ux_helpers import print_next_steps

from kaira.config import (
    TIER_LAYERS,
    LAYER_DIRS,
    get_config,
    save_config,
    register_model,
)
from kaira.core.parser import (
    parse_fields,
    parse_relations_from_json,
    validate_model_name,
    camel_to_snake,
    FieldDef,
    RelationDef,
)
from kaira.core.generator import generate_layer, generate_all, resolve_output_path
from kaira.core.detector import write_with_check

def _ruff_format(path: Path) -> None:
    """Run ruff check --fix and ruff format on the given file path."""
    ruff_bin = shutil.which("ruff")
    if not ruff_bin:
        console.print("  [yellow]⚠️  ruff not found. Install it for auto-formatting:[/yellow]\n"
                      "      [dim]pip install ruff[/dim]")
        return
    try:
        # Run ruff check --fix
        subprocess.run([ruff_bin, "check", "--fix", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Run ruff format
        subprocess.run([ruff_bin, "format", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

app = typer.Typer(help="Scaffold FastAPI backend layers.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_success(path: Path) -> None:
    console.print(f"  [bold green]✓[/bold green]  Written: [cyan]{path}[/cyan]")


def _print_skipped(path: Path) -> None:
    console.print(f"  [yellow]→[/yellow]  Skipped: [dim]{path}[/dim]")


def _register_router_in_main(model_name: str, base: Path, config) -> None:
    """Register a generated router in Phase 3 main.py when the placeholder exists."""
    main_path = base / "main.py"
    if not main_path.exists():
        return

    try:
        content = main_path.read_text(encoding="utf-8")
    except OSError:
        return

    marker = "# [ROUTER_REGISTRATION]"
    if marker not in content:
        return

    snake = camel_to_snake(model_name)
    routers_dir = config.routers_dir.replace("/", ".").replace("\\", ".")
    router_var = f"{snake}_router"
    import_line = f"from {routers_dir}.{snake}_router import router as {router_var}"
    include_line = f"app.include_router({router_var}, prefix=API_VERSION_PREFIX)"

    if import_line not in content:
        import_anchor = "from rate_limit import limiter\n"
        if import_anchor in content:
            content = content.replace(import_anchor, f"{import_anchor}{import_line}\n", 1)
        else:
            content = f"{import_line}\n{content}"

    if include_line not in content:
        content = content.replace(marker, f"{include_line}\n{marker}", 1)

    main_path.write_text(content, encoding="utf-8")


def _generate_and_write(
    layers: list[str],
    model_name: str,
    fields: list[FieldDef],
    relations: list[RelationDef],
    force: bool,
    non_interactive: bool,
) -> None:
    """Render and write the given layers to disk."""
    config = get_config()
    base = Path.cwd()

    for layer in layers:
        content = generate_layer(layer, model_name, fields, relations, config)
        out_path = resolve_output_path(layer, model_name, config, base)
        result = write_with_check(out_path, content, force=force, non_interactive=non_interactive)
        if result == "written":
            _ruff_format(out_path)
            _print_success(out_path)
            if layer == "router":
                _register_router_in_main(model_name, base, config)
        else:
            _print_skipped(out_path)

    # Persist model to .kaira.json
    register_model(
        config,
        model_name,
        [{"name": f.name, "type": f.raw_type} for f in fields],
        [{"type": r.relation_type, "target": r.target} for r in relations],
    )
    save_config(config)


# ---------------------------------------------------------------------------
# generate model
# ---------------------------------------------------------------------------

@app.command("model")
def generate_model(
    model_name: Annotated[str, typer.Argument(help="PascalCase model name, e.g. BlogPost")],
    fields: Annotated[
        Optional[str],
        typer.Option("--fields", "-f", help='Field definitions: "name:str, age:int"'),
    ] = None,
    tier: Annotated[
        str,
        typer.Option("--tier", "-t", help="Complexity tier: simple | full"),
    ] = "full",
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing files without prompting"),
    ] = False,
) -> None:
    """Generate a complete pipeline for MODEL_NAME.

    Examples
    --------
    kaira generate model User --fields "username:str, email:str, age:int"
    kaira generate model Post --tier simple --fields "title:str, body:str"
    """
    try:
        validate_model_name(model_name)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    try:
        parsed_fields = parse_fields(fields or "")
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    if tier not in TIER_LAYERS:
        console.print(
            f"[bold red]✗[/bold red]  Unknown tier '{tier}'. Choose: {list(TIER_LAYERS)}"
        )
        raise typer.Exit(1)

    layers = TIER_LAYERS[tier]
    console.print(
        Panel(
            f"[bold cyan]Model:[/bold cyan] {model_name}\n"
            f"[bold cyan]Tier:[/bold cyan]  {tier}\n"
            f"[bold cyan]Layers:[/bold cyan] {', '.join(layers)}\n"
            f"[bold cyan]Fields:[/bold cyan] {', '.join(f.name for f in parsed_fields) or '—'}",
            title="[bold]Kaira[/bold] — Generating Pipeline",
            border_style="cyan",
        )
    )

    config = get_config()
    base = Path.cwd()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]Generating {model_name}...", total=len(layers))
        for lyr in layers:
            progress.update(task, description=f"[cyan]  {lyr}...")
            content = generate_layer(lyr, model_name, parsed_fields, [], config)
            out_path = resolve_output_path(lyr, model_name, config, base)
            from kaira.core.detector import write_with_check as _wwc
            result = _wwc(out_path, content, force=force, non_interactive=False)
            if result == "written":
                _ruff_format(out_path)
                _print_success(out_path)
                if lyr == "router":
                    _register_router_in_main(model_name, base, config)
            else:
                _print_skipped(out_path)
            progress.advance(task)

    # Persist model to .kaira.json
    register_model(
        config,
        model_name,
        [{"name": f.name, "type": f.raw_type} for f in parsed_fields],
        [],
    )
    save_config(config)

    console.print(f"\n[bold green]✓[/bold green]  Done! Pipeline generated for [bold]{model_name}[/bold].")

    # Derive next steps from project state
    db_type = config.db_type
    output_root = base / config.output_dir
    next_steps: list[str] = []
    if db_type != "mongodb" and not (output_root / "alembic").exists():
        next_steps.append("[cyan]kaira migrate init[/cyan] — set up Alembic migrations")
    if not (output_root / "auth" / "dependencies.py").exists():
        next_steps.append("[cyan]kaira auth generate --type jwt[/cyan] — add authentication")
    if not (output_root / "tests").exists():
        next_steps.append(f"[cyan]kaira test generate {model_name}[/cyan] — generate tests")
    next_steps.append(f"[cyan]kaira diff {model_name}[/cyan] — preview future changes")
    print_next_steps(next_steps)


# ---------------------------------------------------------------------------
# Single-layer commands
# ---------------------------------------------------------------------------

def _single_layer_cmd(layer: str, model_name: str, fields_str: Optional[str], force: bool) -> None:
    try:
        validate_model_name(model_name)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    try:
        parsed_fields = parse_fields(fields_str or "")
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    config = get_config()
    content = generate_layer(layer, model_name, parsed_fields, [], config)
    out_path = resolve_output_path(layer, model_name, config, Path.cwd())
    result = write_with_check(out_path, content, force=force, non_interactive=False)
    if result == "written":
        _ruff_format(out_path)
        _print_success(out_path)
    else:
        _print_skipped(out_path)


@app.command("router")
def generate_router(
    model_name: Annotated[str, typer.Argument(help="PascalCase model name")],
    fields: Annotated[Optional[str], typer.Option("--fields", "-f")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Generate only the FastAPI router for MODEL_NAME."""
    _single_layer_cmd("router", model_name, fields, force)


@app.command("service")
def generate_service(
    model_name: Annotated[str, typer.Argument(help="PascalCase model name")],
    fields: Annotated[Optional[str], typer.Option("--fields", "-f")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Generate only the service layer for MODEL_NAME."""
    _single_layer_cmd("service", model_name, fields, force)


@app.command("schema")
def generate_schema(
    model_name: Annotated[str, typer.Argument(help="PascalCase model name")],
    fields: Annotated[Optional[str], typer.Option("--fields", "-f")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Generate only the Pydantic schemas for MODEL_NAME."""
    _single_layer_cmd("schema", model_name, fields, force)


@app.command("repository")
def generate_repository(
    model_name: Annotated[str, typer.Argument(help="PascalCase model name")],
    fields: Annotated[Optional[str], typer.Option("--fields", "-f")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Generate only the repository layer for MODEL_NAME."""
    _single_layer_cmd("repository", model_name, fields, force)


# ---------------------------------------------------------------------------
# Bulk generation
# ---------------------------------------------------------------------------

@app.command("bulk")
def generate_bulk(
    json_file: Annotated[str, typer.Argument(help="Path to bulk models JSON file")],
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Bulk-generate models from a JSON definition file.

    The JSON file should be an array of model definitions:

    \b
    [
      {"name": "User", "fields": {"username": "str", "email": "str"}},
      {"name": "Post", "fields": {"title": "str", "body": "str"},
       "relations": [{"type": "many-to-one", "target": "User"}]}
    ]
    """
    json_path = Path(json_file)
    if not json_path.exists():
        console.print(f"[bold red]✗[/bold red]  File not found: {json_file}")
        raise typer.Exit(1)

    try:
        with open(json_path, encoding="utf-8") as f:
            models_data = json.load(f)
    except json.JSONDecodeError as exc:
        console.print(f"[bold red]✗[/bold red]  Invalid JSON: {exc}")
        raise typer.Exit(1)

    if not isinstance(models_data, list):
        console.print("[bold red]✗[/bold red]  JSON root must be an array of model definitions.")
        raise typer.Exit(1)

    config = get_config()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Generating models...", total=len(models_data))

        for entry in models_data:
            model_name = entry.get("name", "")
            try:
                validate_model_name(model_name)
            except ValueError as exc:
                console.print(f"[bold red]✗[/bold red]  Skipping '{model_name}': {exc}")
                progress.advance(task)
                continue

            # Parse fields — support both dict format and string format
            raw_fields = entry.get("fields", {})
            if isinstance(raw_fields, dict):
                fields_str = ", ".join(f"{k}:{v}" for k, v in raw_fields.items())
            else:
                fields_str = str(raw_fields)

            try:
                parsed_fields = parse_fields(fields_str)
            except ValueError as exc:
                console.print(f"[bold red]✗[/bold red]  Skipping '{model_name}': {exc}")
                progress.advance(task)
                continue

            relations_data = entry.get("relations", [])
            try:
                parsed_relations = parse_relations_from_json(relations_data)
            except ValueError as exc:
                console.print(f"[bold red]✗[/bold red]  Skipping '{model_name}': {exc}")
                progress.advance(task)
                continue

            tier = entry.get("tier", "full")
            layers = TIER_LAYERS.get(tier, TIER_LAYERS["full"])

            progress.update(task, description=f"[cyan]Generating {model_name}...")
            _generate_and_write(layers, model_name, parsed_fields, parsed_relations, force, non_interactive=True)
            progress.advance(task)

    console.print(f"\n[bold green]✓[/bold green]  Bulk generation complete! Processed {len(models_data)} model(s).")
