"""Generate command group — scaffold 5-layer pipelines."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel

from kaira.console import console
from kaira.commands.ux_helpers import print_next_steps

from kaira.config import (
    TIER_LAYERS,
    get_config,
    save_config,
    register_model,
    register_embedded_model,
    embedded_model_names,
)
from kaira.core.parser import (
    parse_fields,
    parse_relations_from_json,
    validate_model_name,
    camel_to_snake,
    FieldDef,
    RelationDef,
)
from kaira.core.generator import (
    generate_layer,
    generate_embedded_model,
    resolve_output_path,
    TEMPLATES_DIR,
)
from kaira.core.detector import write_with_check
from kaira.core.wiring import register_router_in_main


def _ensure_message_schema(config, base: Path) -> None:
    """Write the shared ``MessageResponse`` schema once if it does not exist.

    Every generated router imports this schema for the delete response, so
    it must be present before the first router is used.
    """
    schemas_dir = base / config.schemas_dir
    target = schemas_dir / "message_schema.py"
    if target.exists():
        return
    schemas_dir.mkdir(parents=True, exist_ok=True)
    (schemas_dir / "__init__.py").touch(exist_ok=True)
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    tmpl = env.get_template("message_schema.py.j2")
    target.write_text(tmpl.render(), encoding="utf-8")


def _ruff_format(path: Path) -> None:
    """Run ruff check --fix and ruff format on the given file path."""
    ruff_bin = shutil.which("ruff")
    if not ruff_bin:
        console.print(
            "  [yellow]⚠️  ruff not found. Install it for auto-formatting:[/yellow]\n"
            "      [dim]pip install ruff[/dim]"
        )
        return
    try:
        # Run ruff check --fix
        subprocess.run(
            [ruff_bin, "check", "--fix", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Run ruff format
        subprocess.run(
            [ruff_bin, "format", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


app = typer.Typer(help="Scaffold FastAPI backend layers.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _relative_to(path: Path, base: Path) -> str:
    """Return *path* relative to *base*, falling back to the file name."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return path.name


def _print_success(path: Path) -> None:
    console.print(f"  [bold green]✓[/bold green]  Written: [cyan]{path}[/cyan]")


def _print_skipped(path: Path) -> None:
    console.print(f"  [yellow]→[/yellow]  Skipped: [dim]{path}[/dim]")


def _register_router_in_main(model_name: str, base: Path, config) -> None:
    """Register a generated router in Phase 3 main.py when the placeholder exists."""
    snake = camel_to_snake(model_name)
    routers_dir = config.routers_dir.replace("/", ".").replace("\\", ".")
    router_var = f"{snake}_router"
    register_router_in_main(
        base / "main.py",
        f"from {routers_dir}.{snake}_router import router as {router_var}",
        f"app.include_router({router_var}, prefix=API_VERSION_PREFIX)",
    )


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
        result = write_with_check(
            out_path, content, force=force, non_interactive=non_interactive
        )
        if result == "written":
            _ruff_format(out_path)
            _print_success(out_path)
            if layer == "router":
                _register_router_in_main(model_name, base, config)
                _ensure_message_schema(config, base)
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
# generate embedded
# ---------------------------------------------------------------------------


@app.command("embedded")
def generate_embedded(
    model_name: Annotated[
        str, typer.Argument(help="PascalCase embedded type name, e.g. EmergencyContact")
    ],
    fields: Annotated[
        Optional[str],
        typer.Option("--fields", "-f", help='Field definitions: "name:str, phone:str"'),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing files without prompting"),
    ] = False,
) -> None:
    """Generate an embedded (nested) document type usable as a field type.

    An embedded type is a value object stored *inside* another model rather
    than in its own collection or table — so it gets a single pydantic model,
    no repository, service or router. Once generated, any model can declare it:

    \b
    kaira generate embedded EmergencyContact --fields "name:str, phone:str"
    kaira generate model Credential --fields "sss_id:str, emergency_contact:EmergencyContact"

    Optional and list forms both work:

    \b
    --fields "emergency_contact:Optional[EmergencyContact]"
    --fields "contacts:list[EmergencyContact]"
    """
    try:
        validate_model_name(model_name)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    config = get_config()

    # An embedded type may itself embed another, so already-registered names
    # are in scope — minus this one, which cannot contain itself.
    in_scope = embedded_model_names(config) - {model_name}
    try:
        parsed_fields = parse_fields(fields or "", embedded=in_scope)
    except ValueError as exc:
        console.print(f"[bold red]✗[/bold red]  {exc}")
        raise typer.Exit(1)

    if any(m.get("name") == model_name for m in config.generated_models):
        console.print(
            f"[bold red]✗[/bold red]  '{model_name}' is already a top-level model. "
            f"An embedded type cannot share its name."
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold cyan]Embedded:[/bold cyan] {model_name}\n"
            f"[bold cyan]Fields:[/bold cyan]   "
            f"{', '.join(f.name for f in parsed_fields) or '—'}\n"
            f"[dim]Nested value object — no repository, service or router.[/dim]",
            title="[bold]Kaira[/bold] — Generating Embedded Type",
            border_style="cyan",
        )
    )

    base = Path.cwd()
    content = generate_embedded_model(model_name, parsed_fields, config)
    out_path = resolve_output_path("model", model_name, config, base)
    result = write_with_check(out_path, content, force=force, non_interactive=False)
    if result == "written":
        _ruff_format(out_path)
        _print_success(out_path)
    else:
        _print_skipped(out_path)

    register_embedded_model(
        config,
        model_name,
        [{"name": f.name, "type": f.raw_type} for f in parsed_fields],
    )
    save_config(config)

    print_next_steps(
        [
            f'Use it: kaira generate model Owner --fields "{camel_to_snake(model_name)}:{model_name}"',
            "Already have the owning model? kaira sync model Owner cascades it "
            "through schema and router.",
        ]
    )


# ---------------------------------------------------------------------------
# generate model
# ---------------------------------------------------------------------------


@app.command("model")
def generate_model(
    model_name: Annotated[
        str, typer.Argument(help="PascalCase model name, e.g. BlogPost")
    ],
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
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Non-interactive mode."),
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

    from kaira.core.progress import ProgressItem, ProgressPhase, ProgressRenderer

    items = [ProgressItem(name=lyr) for lyr in layers]
    phase = ProgressPhase(name="scaffold", items=items)
    renderer = ProgressRenderer(
        title=f"generate model {model_name}",
        total=len(layers),
        phases=[phase],
        unit="layers",
    )

    written_count = 0
    with renderer:
        phase.start()
        renderer.refresh()
        for lyr, item in zip(layers, items):
            item.start()
            renderer.refresh()
            content = generate_layer(lyr, model_name, parsed_fields, [], config)
            out_path = resolve_output_path(lyr, model_name, config, base)
            from kaira.core.detector import write_with_check as _wwc

            result = _wwc(out_path, content, force=force, non_interactive=False)
            if result == "written":
                _ruff_format(out_path)
                _print_success(out_path)
                if lyr == "router":
                    _register_router_in_main(model_name, base, config)
                item.done(detail=_relative_to(out_path, base))
                written_count += 1
            else:
                _print_skipped(out_path)
                item.done(detail="skipped")
            renderer.refresh()

        phase.finish(f"{written_count} of {len(layers)} written")
        renderer.refresh()
    renderer.print_result()

    # Ensure the shared MessageResponse schema exists alongside model schemas.
    _ensure_message_schema(config, base)

    # Persist model to .kaira.json
    register_model(
        config,
        model_name,
        [{"name": f.name, "type": f.raw_type} for f in parsed_fields],
        [],
    )
    save_config(config)

    console.print(
        f"\n[bold green]✓[/bold green]  Done! Pipeline generated for [bold]{model_name}[/bold]."
    )

    # Prompt to regenerate documentation if present and out of sync
    from kaira.core.docs_render import maybe_autodocs

    maybe_autodocs(quiet=quiet)

    # Derive next steps from project state
    db_type = config.db_type
    output_root = base / config.output_dir
    next_steps: list[str] = []
    if db_type != "mongodb" and not (output_root / "alembic").exists():
        next_steps.append("[cyan]kaira migrate init[/cyan] — set up Alembic migrations")
    if not (output_root / "auth" / "dependencies.py").exists():
        next_steps.append(
            "[cyan]kaira auth generate --type jwt[/cyan] — add authentication"
        )
    if not (output_root / "tests").exists():
        next_steps.append(
            f"[cyan]kaira test generate {model_name}[/cyan] — generate tests"
        )
    next_steps.append(f"[cyan]kaira diff {model_name}[/cyan] — preview future changes")
    print_next_steps(next_steps, quiet=quiet)


# ---------------------------------------------------------------------------
# Single-layer commands
# ---------------------------------------------------------------------------


def _single_layer_cmd(
    layer: str, model_name: str, fields_str: Optional[str], force: bool
) -> None:
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
        console.print(
            "[bold red]✗[/bold red]  JSON root must be an array of model definitions."
        )
        raise typer.Exit(1)

    from kaira.core.progress import ProgressItem, ProgressPhase, ProgressRenderer

    items = [ProgressItem(name=entry.get("name", "unknown")) for entry in models_data]
    phase = ProgressPhase(name="bulk generate", items=items)
    renderer = ProgressRenderer(
        title="generating", total=len(models_data), phases=[phase], unit="models"
    )

    with renderer:
        phase.start()
        renderer.refresh()
        for entry, item in zip(models_data, items):
            model_name = entry.get("name", "")
            item.start()
            renderer.refresh()
            try:
                validate_model_name(model_name)
            except ValueError as exc:
                console.print(f"[bold red]✗[/bold red]  Skipping '{model_name}': {exc}")
                item.fail(reason=str(exc))
                renderer.refresh()
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
                item.fail(reason=str(exc))
                renderer.refresh()
                continue

            relations_data = entry.get("relations", [])
            try:
                parsed_relations = parse_relations_from_json(relations_data)
            except ValueError as exc:
                console.print(f"[bold red]✗[/bold red]  Skipping '{model_name}': {exc}")
                item.fail(reason=str(exc))
                renderer.refresh()
                continue

            tier = entry.get("tier", "full")
            layers = TIER_LAYERS.get(tier, TIER_LAYERS["full"])

            _generate_and_write(
                layers,
                model_name,
                parsed_fields,
                parsed_relations,
                force,
                non_interactive=True,
            )
            item.done(detail=f"{len(layers)} layers")
            renderer.refresh()

        phase.finish()
        renderer.refresh()
    renderer.print_result()

    console.print(
        f"\n[bold green]✓[/bold green]  Bulk generation complete! Processed {len(models_data)} model(s)."
    )
