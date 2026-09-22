"""Database seeding command group."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Annotated, Any

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.prompt import Confirm

from kaira.config import (
    SERVER_MANAGED_FIELDS,
    SUPPORTED_FIELD_TYPES,
    embedded_model_names,
    get_config,
    save_config,
)
from kaira.console import console
from kaira.core.aliases import complete_model_name
from kaira.core.detector import write_with_check
from kaira.core.drivers import get_engine_driver
from kaira.core.parser import (
    _embedded_target,
    camel_to_snake,
    infer_column_type,
    normalize_ast_type,
    snake_to_pascal,
    table_name,
)
from kaira.core.project_runner import run_project_file, run_project_script
from kaira.core.stats import build_stats_table, counts_by_name, try_collect_db_stats

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Database seeding commands.")

_MANAGED_FIELDS = SERVER_MANAGED_FIELDS


def _embedded_seed_type(raw_type: str, embedded: set[str]) -> str | None:
    """Return the canonical embedded type for *raw_type*, or ``None``.

    Mirrors the check in ``sync``: without it an embedded field is dropped from
    the seed, and a seed missing a *required* nested field fails validation the
    moment it runs.
    """
    if not embedded:
        return None
    target = _embedded_target(raw_type)
    if target is None or target not in embedded:
        return None
    raw = raw_type.strip()
    if raw.lower().startswith("list["):
        return f"list[{target}]"
    if raw.startswith("Optional["):
        return f"Optional[{target}]"
    return target


def _parse_live_model_fields(
    model_file: Path,
    target_model_name: str | None = None,
    embedded: set[str] | None = None,
) -> list[dict[str, str]]:
    """Inspect a generated Python model file via AST and extract active fields.

    Handles Beanie/Pydantic Document models, SQLAlchemy Mapped models, and
    embedded document fields whose type names a registered embedded model.
    """
    embedded = embedded or set()
    if not model_file.exists():
        return []

    try:
        tree = ast.parse(model_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    target_node: ast.ClassDef | None = None
    if target_model_name:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == target_model_name:
                target_node = node
                break

    if target_node is None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name in ("Settings", "Config"):
                continue
            is_enum = any(
                (isinstance(b, ast.Name) and b.id == "Enum")
                or (isinstance(b, ast.Attribute) and b.attr == "Enum")
                for b in node.bases
            )
            if is_enum:
                continue
            target_node = node
            break

    if target_node is None:
        return []

    fields: list[dict[str, str]] = []
    for stmt in target_node.body:
        name = ""
        stmt_val: ast.expr | None = None

        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            stmt_val = stmt.value
        elif (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            name = stmt.targets[0].id
            stmt_val = stmt.value

        if not name or name in _MANAGED_FIELDS or name.startswith("_"):
            continue

        norm_type: str | None = None
        if isinstance(stmt, ast.AnnAssign):
            raw_type = ""
            try:
                raw_type = ast.unparse(stmt.annotation).strip().strip('"').strip("'")
            except Exception:
                raw_type = ""

            if raw_type.startswith("Mapped[") and raw_type.endswith("]"):
                raw_type = raw_type[7:-1].strip()

            # Checked before the generic exclusions so `list[EmergencyContact]`
            # is not mistaken for a relationship and discarded.
            if raw_type:
                embedded_type = _embedded_seed_type(raw_type, embedded)
                if embedded_type:
                    fields.append({"name": name, "type": embedded_type})
                    continue

            if raw_type and not any(
                token in raw_type
                for token in ("Link[", "relationship", "ForeignKey", "list[", "Dict[")
            ):
                norm_type = normalize_ast_type(raw_type)

        if norm_type is None and stmt_val is not None:
            norm_type = infer_column_type(stmt_val)

        if norm_type and norm_type in SUPPORTED_FIELD_TYPES:
            fields.append({"name": name, "type": norm_type})

    return fields


def _restore_embedded_from_snapshot(
    live_fields: list[dict[str, str]],
    snapshot: list[dict[str, str]],
    embedded: set[str],
) -> list[dict[str, str]]:
    """Re-add embedded fields the AST pass could not recover.

    On SQL an embedded field is declared as ``Mapped[dict]`` backed by a JSON
    column, so the model file no longer names the embedded type — only the
    ``.kaira.json`` snapshot still knows it. Merging the two keeps SQL seeds
    complete *and* stops the snapshot from being overwritten with a field list
    that has silently lost its embedded entries.
    """
    live_names = {f["name"] for f in live_fields}
    merged = list(live_fields)
    for index, field in enumerate(snapshot):
        if field.get("name") in live_names:
            continue
        if _embedded_seed_type(field.get("type", ""), embedded):
            merged.insert(min(index, len(merged)), field)
    return merged


def _get_model_fields(
    config: Any, model_name: str, output_root: Path
) -> list[dict[str, str]]:
    """Resolve model fields, preferring live AST inspection of the model file over static config."""
    snake = camel_to_snake(model_name)
    model_file = output_root / config.models_dir / f"{snake}.py"
    embedded = embedded_model_names(config)

    live_fields = _parse_live_model_fields(model_file, model_name, embedded)
    if live_fields:
        for m in config.generated_models:
            if m.get("name") == model_name:
                live_fields = _restore_embedded_from_snapshot(
                    live_fields, m.get("fields", []), embedded
                )
                m["fields"] = live_fields
                save_config(config)
                break
        return live_fields

    model_entry = next(
        (m for m in config.generated_models if m.get("name") == model_name), None
    )
    return model_entry.get("fields", []) if model_entry else []


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _is_password_field(field: dict[str, Any]) -> bool:
    """Whether a field is hashed at seed time, requiring bcrypt in the script.

    Must stay in step with the password branch of ``_seed_macros.j2``.
    """
    name = str(field.get("name", "")).lower()
    return name == "password" or name.endswith("_password")


def _resolve_database_url() -> str:
    """Resolve the active DATABASE_URL using the same precedence as `kaira db`."""
    from kaira.commands.db_cmd import _get_database_url

    return _get_database_url()


def _snapshot_counts(db_type: str) -> dict[str, int] | None:
    """Capture current per-entity row/document counts, or None if unavailable."""
    url = _resolve_database_url()
    if not url:
        return None
    result = try_collect_db_stats(db_type, url)
    return counts_by_name(result[1]) if result else None


def render_seed(
    model_name: str,
    config: Any,
    output_root: Path,
    fields_override: list[dict[str, str]] | None = None,
) -> tuple[str, Path]:
    """Render a seed script and return ``(content, output_path)``.

    Shared by ``seed generate`` and ``sync`` so the template context
    assembly lives in exactly one place.

    Args:
        model_name: PascalCase model name.
        config: Loaded :class:`KairaConfig`.
        output_root: Project output root (``cwd / config.output_dir``).
        fields_override: If given, use these field dicts instead of
            inspecting the model file / config snapshot.

    Returns:
        A ``(rendered_source, seed_file_path)`` tuple.
    """
    fields = (
        fields_override
        if fields_override is not None
        else _get_model_fields(config, model_name, output_root)
    )

    db_type = getattr(config, "db_type", "sqlite")
    driver = get_engine_driver(db_type)

    env = _get_env()
    snake = camel_to_snake(model_name)
    # Embedded types need their own field lists so the seed can build a nested
    # sample value instead of a flat string. Keyed by type name for the macro.
    embedded_defs = {
        entry["name"]: entry.get("fields", [])
        for entry in getattr(config, "embedded_models", [])
        if entry.get("name")
    }
    embedded_used = {
        _embedded_target(f.get("type", "")) or ""
        for f in fields
        if _embedded_seed_type(f.get("type", ""), set(embedded_defs))
    }

    # A seeded password is bcrypt-hashed and unreadable afterwards, so the seed
    # prints the plaintext and the identifier it pairs with. The generated auth
    # service authenticates against `User.username`, so that field is preferred;
    # email is the fallback for models shaped differently.
    has_password = any(_is_password_field(f) for f in fields) or any(
        _is_password_field(sub)
        for name in embedded_used
        for sub in embedded_defs.get(name, [])
    )
    field_names = [f.get("name") for f in fields]
    login_identifier = next(
        (name for name in ("username", "email") if name in field_names), ""
    )
    auth_type = getattr(config, "auth_type", "none")
    api_version = getattr(config, "api_version", "v1")

    ctx = {
        "model_name": model_name,
        "snake_name": snake,
        "table_name": table_name(model_name),
        "fields": fields,
        "models_dir": config.models_dir,
        "db_type": db_type,
        "embedded_defs": embedded_defs,
        "has_password": has_password,
        "login_identifier": login_identifier,
        # The curl hint is only correct for the model the auth service queries.
        "is_auth_model": model_name == "User" and auth_type != "none",
        "auth_login_path": f"/api/{api_version}/auth/login",
        # A password *inside* an embedded type still needs bcrypt imported.
        "needs_bcrypt": has_password,
    }

    tmpl = env.get_template(driver.get_seed_template_name())
    seeds_dir = output_root / "seeds"
    out_path = seeds_dir / f"seed_{snake}.py"
    return tmpl.render(**ctx), out_path


@app.command("generate")
def seed_generate(
    model_name: Annotated[
        str, typer.Argument(help="Name of the model to generate a seed file for.")
    ],
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files.")
    ] = False,
) -> None:
    """Generate a mock data seed script for a model."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    seeds_dir = output_root / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    (seeds_dir / "__init__.py").touch(exist_ok=True)

    content, out_path = render_seed(model_name, config, output_root)
    result = write_with_check(out_path, content, force=force)
    if result == "written":
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")
    else:
        console.print(f"  [blue]→[/blue]  Skipped: [dim]{out_path}[/dim]")


@app.command("run")
def seed_run(
    model_name: Annotated[
        str | None,
        typer.Argument(
            help="Name of the model to seed.",
            autocompletion=complete_model_name,
        ),
    ] = None,
    seed_all: Annotated[
        bool, typer.Option("--all", help="Run all seed scripts.")
    ] = False,
    count: Annotated[
        int, typer.Option("--count", help="Records to insert per model.")
    ] = 5,
    force: Annotated[
        bool,
        typer.Option("--force", help="Seed even if the table/collection is non-empty."),
    ] = False,
    stats: Annotated[
        bool,
        typer.Option(
            "--stats/--no-stats", help="Show table/collection counts afterwards."
        ),
    ] = True,
) -> None:
    """Run database seed scripts (development/staging only)."""
    # Enforce settings APP_ENV safety check
    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production":
        console.print(
            "[red]Error: Seeding is disabled in production to protect data![/red]"
        )
        raise typer.Exit(1)

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    seeds_dir = output_root / "seeds"
    db_type = getattr(config, "db_type", "sqlite")

    if not seeds_dir.exists():
        console.print(
            "[yellow]No seeds directory found. Run kaira seed generate <Model> first.[/yellow]"
        )
        return

    scripts = []
    if seed_all:
        scripts = sorted(seeds_dir.glob("seed_*.py"))
    elif model_name:
        snake = camel_to_snake(model_name)
        target = seeds_dir / f"seed_{snake}.py"
        if not target.exists():
            console.print(f"[red]Seed script not found:[/red] {target}")
            raise typer.Exit(1)
        scripts = [target]
    else:
        console.print("[red]Error: Must specify either a model name or --all[/red]")
        raise typer.Exit(1)

    before = _snapshot_counts(db_type) if stats else None

    failures: list[str] = []
    from kaira.core.progress import ProgressItem, ProgressPhase, ProgressRenderer

    items = [ProgressItem(name=s.name) for s in scripts]
    phase = ProgressPhase(name="seeding", items=items)
    renderer = ProgressRenderer(
        title="seeding", total=len(scripts), phases=[phase], unit="scripts"
    )

    with renderer:
        phase.start()
        renderer.refresh()
        for script, item in zip(scripts, items):
            item.start()
            renderer.refresh()
            # Auto-sync live model fields into seed script if model definition evolved.
            sname = script.stem.replace("seed_", "")
            model_pascal = snake_to_pascal(sname)
            model_file = output_root / config.models_dir / f"{sname}.py"
            live_fields = _parse_live_model_fields(
                model_file, model_pascal, embedded_model_names(config)
            )
            if live_fields:
                script_text = script.read_text(encoding="utf-8")
                missing = [
                    f["name"]
                    for f in live_fields
                    if f"'{f['name']}':" not in script_text
                    and f'"{f["name"]}":' not in script_text
                ]
                if missing:
                    content, _ = render_seed(
                        model_pascal, config, output_root, fields_override=live_fields
                    )
                    write_with_check(script, content, force=True, non_interactive=True)
                    console.print(
                        f"  [cyan]ℹ Auto-synced {script.name} with updated model fields: {', '.join(missing)}[/cyan]"
                    )

            args = ["--count", str(count)] + (["--force"] if force else [])
            result = run_project_file(script, output_root, args=args)

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip():
                        console.print(f"  [green bold]✓[/green bold]  {line.strip()}")
                item.done()
            else:
                failures.append(script.name)
                detail = (result.stderr or result.stdout).strip().splitlines()
                tail = "\n".join(detail[-6:]) if detail else "no output"
                console.print(
                    f"  [red bold]✗[/red bold]  {script.name} failed:\n[dim]{tail}[/dim]"
                )
                item.fail(
                    reason=tail.splitlines()[0] if tail != "no output" else "failed"
                )
            renderer.refresh()

        phase.finish()
        renderer.refresh()
    renderer.print_result()

    if stats:
        _print_seed_stats(db_type, before)

    if failures:
        console.print(
            Panel(
                f"[red]❌ {len(failures)} of {len(scripts)} seed script(s) failed: "
                f"{', '.join(failures)}[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)


def _print_seed_stats(db_type: str, before: dict[str, int] | None) -> None:
    """Render post-seed table/collection counts, with a delta when available."""
    url = _resolve_database_url()
    if not url:
        console.print("[dim]Skipping stats: DATABASE_URL is not configured.[/dim]")
        return

    result = try_collect_db_stats(db_type, url)
    if result is None:
        console.print("[dim]Skipping stats: could not read the database.[/dim]")
        return

    db_name, rows = result
    if not rows:
        console.print("[dim]No tables or collections found yet.[/dim]")
        return

    label = "collection" if get_engine_driver(db_type).is_document_db else "table"
    console.print()
    console.print(
        build_stats_table(
            db_type,
            db_name,
            rows,
            before=before,
            title=f"⚡ Khaira — After Seeding ({db_type.upper()}: [cyan]{db_name}[/cyan])",
        )
    )
    total = sum(row.get("count", 0) for row in rows)
    console.print(f"\n[dim]{len(rows)} {label}(s), {total} record(s) total.[/dim]")


_CLEAR_DOC_SCRIPT = """
import asyncio

from core.database import BINDING, close_db, discover_document_models, init_db, resolve_db_name
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    await init_db(discover_document_models())
    client = AsyncIOMotorClient(BINDING.url)
    try:
        db = client[resolve_db_name()]
        for name in await db.list_collection_names():
            # delete_many keeps the collection (and its indexes) visible in
            # Compass; dropping it would hide the schema again.
            result = await db[name].delete_many({})
            print(f"{name}: removed {result.deleted_count} document(s)")
    finally:
        client.close()
        await close_db()


asyncio.run(main())
"""

_CLEAR_SQL_SCRIPT = """
import asyncio
import importlib
import pathlib
import pkgutil

from core.database import Base, engine

models_dir = pathlib.Path("models")
if models_dir.is_dir():
    for mod in pkgutil.iter_modules([str(models_dir)]):
        if not mod.name.startswith("_"):
            importlib.import_module(f"models.{mod.name}")


async def main():
    async with engine.begin() as conn:
        # Delete rather than drop so the schema survives; reverse order respects
        # foreign keys.
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
            print(f"{table.name}: cleared")
    await engine.dispose()


asyncio.run(main())
"""


@app.command("clear")
def seed_clear(
    force: Annotated[
        bool, typer.Option("--force", help="Skip the confirmation prompt.")
    ] = False,
) -> None:
    """Clear all data from generated database tables or collections (requires confirmation)."""
    app_env = os.getenv("APP_ENV", "development")
    if app_env == "production":
        console.print("[red]Error: Database clearing is disabled in production![/red]")
        raise typer.Exit(1)

    if not force and not Confirm.ask(
        "[yellow]⚠  Are you sure you want to clear all data from database tables/collections?[/yellow]"
    ):
        console.print("Operation cancelled.")
        return

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    db_type = getattr(config, "db_type", "sqlite")
    driver = get_engine_driver(db_type)

    console.print("[cyan]Clearing database data...[/cyan]")
    script = _CLEAR_DOC_SCRIPT if driver.is_document_db else _CLEAR_SQL_SCRIPT
    result = run_project_script(script, output_root)

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        tail = "\n".join(detail[-6:]) if detail else "no output"
        console.print(
            Panel(
                f"[red]Error clearing database:[/red]\n[dim]{tail}[/dim]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    for line in result.stdout.splitlines():
        if line.strip():
            console.print(f"  [dim]{line.strip()}[/dim]")
    console.print("[green]✔ Database cleared successfully![/green]")
