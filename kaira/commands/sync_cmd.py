"""Kaira sync command group — cascade model field changes across all layers.

``kaira sync model`` closes the *field-refresh gap*: after a field is added to
(or removed from) a model, this command regenerates the mechanical layers
(schema, router) so they stay in step with the model, updates the field snapshot
in ``.kaira.json``, and flags the service layer for manual review instead of
overwriting hand-written business logic.

Per-layer safety
----------------
========== =========================================== ========================
Layer      Action                                      Safety
========== =========================================== ========================
model      Apply field changes                         Overwrite with confirm
schema     Regenerate (mirrors model fields)           Confirm per file
router     Regenerate (re-point schema refs)           Confirm per file
repository Untouched                                   Skip by default
service    Flagged for manual review                   Never auto-rewritten
========== =========================================== ========================
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Annotated, Optional

import typer

from kaira.config import (
    SUPPORTED_FIELD_TYPES,
    KairaConfig,
    get_config,
    register_model,
    save_config,
)
from kaira.console import console
from kaira.core.detector import write_with_check
from kaira.core.generator import generate_layer, resolve_output_path
from kaira.core.parser import (
    FieldDef,
    RelationDef,
    parse_fields,
    parse_relations_from_json,
    validate_model_name,
)
from kaira.core.theme import Theme, sym
from kaira.core.ui import panel, with_summary
from kaira.commands.smart_errors import smart_error
from kaira.commands.ux_helpers import require_project, typed_confirmation

app = typer.Typer(help="Synchronise model field changes across all layers.")

# Columns the generator manages itself — never treated as user fields.
_MANAGED_FIELDS = {"id", "uuid", "created_at", "updated_at"}

# Layers regenerated mechanically from the model's fields.
_CASCADE_LAYERS = ("model", "schema", "router")

# Database types with no relational schema to cascade Alembic-style, but whose
# model/schema/router still regenerate normally.
_DOCUMENT_DB_TYPES = {"mongodb", "atlas", "firebase", "firestore"}


# ---------------------------------------------------------------------------
# Model-file introspection (read fields back from an edited model)
# ---------------------------------------------------------------------------


def _mapped_inner_type(annotation: ast.expr) -> Optional[str]:
    """Return the inner type of a ``Mapped[...]`` annotation, or ``None``.

    Example: ``Mapped[Optional[str]]`` → ``"Optional[str]"``.
    """
    if (
        isinstance(annotation, ast.Subscript)
        and isinstance(annotation.value, ast.Name)
        and annotation.value.id == "Mapped"
    ):
        try:
            return ast.unparse(annotation.slice).strip().strip('"').strip("'")
        except Exception:
            return None
    return None


def _is_relationship_or_fk(value: Optional[ast.expr]) -> bool:
    """Return True when a column assignment is a relationship or foreign key.

    These are managed by the relationship system, not plain user fields, so
    ``sync`` must not treat them as scalar fields.
    """
    if value is None:
        return False
    for node in ast.walk(value):
        if isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name in ("relationship", "ForeignKey"):
                return True
    return False


def _parse_model_fields(model_path: Path) -> Optional[list[FieldDef]]:
    """Read user-defined scalar fields back from a generated model file via AST.

    Returns a list of :class:`FieldDef`, or ``None`` if the file cannot be parsed
    (in which case the caller falls back to the ``.kaira.json`` snapshot).
    """
    try:
        tree = ast.parse(model_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    fields: list[FieldDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.AnnAssign) or not isinstance(
                stmt.target, ast.Name
            ):
                continue
            name = stmt.target.id
            if name in _MANAGED_FIELDS or _is_relationship_or_fk(stmt.value):
                continue
            raw_type = _mapped_inner_type(stmt.annotation)
            if raw_type in SUPPORTED_FIELD_TYPES:
                fields.append(FieldDef(name=name, raw_type=raw_type))  # type: ignore[arg-type]
        break  # Only the first class (the model itself).
    return fields


# ---------------------------------------------------------------------------
# Field merging
# ---------------------------------------------------------------------------


def _snapshot_fields(entry: dict) -> list[FieldDef]:
    """Rebuild :class:`FieldDef` objects from a ``.kaira.json`` model entry."""
    return [
        FieldDef(name=f["name"], raw_type=f["type"])
        for f in entry.get("fields", [])
        if f.get("type") in SUPPORTED_FIELD_TYPES
    ]


def _snapshot_relations(entry: dict) -> list[RelationDef]:
    """Rebuild :class:`RelationDef` objects from a ``.kaira.json`` model entry."""
    try:
        return parse_relations_from_json(entry.get("relations", []))
    except ValueError:
        return []


def _merge_fields(base: list[FieldDef], extra: list[FieldDef]) -> list[FieldDef]:
    """Merge *extra* fields into *base*, overriding by name and appending new ones."""
    by_name = {f.name: f for f in base}
    for f in extra:
        by_name[f.name] = f
    return list(by_name.values())


# ---------------------------------------------------------------------------
# kaira sync model
# ---------------------------------------------------------------------------


@app.command("model")
@with_summary
def sync_model(
    model_name: Annotated[
        Optional[str],
        typer.Argument(help="PascalCase model name to sync (omit with --all)."),
    ] = None,
    fields: Annotated[
        Optional[str],
        typer.Option(
            "--fields", "-f", help='Fields to add/update: "phone:str, verified:bool"'
        ),
    ] = None,
    all_models: Annotated[
        bool,
        typer.Option("--all", help="Sync every model registered in .kaira.json."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show the per-layer plan and change nothing."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Overwrite regenerated layers without confirming."
        ),
    ] = False,
) -> None:
    """Cascade model field changes through schema and router; flag the service.

    Examples
    --------
    kaira sync model User
    kaira sync model User --fields "phone:str, verified:bool"
    kaira sync model User --dry-run
    kaira sync model --all
    """
    require_project()
    config = get_config()

    if all_models:
        targets = [m["name"] for m in config.generated_models]
        if not targets:
            smart_error(
                context="No models registered in .kaira.json to sync.",
                fix_cmd='kaira generate model User --fields "name:str"',
                guide_topic="generate",
            )
        for name in targets:
            _sync_one(name, None, dry_run, force, config)
    else:
        if not model_name:
            smart_error(
                context="Provide a model name or use --all.",
                fix_cmd="kaira sync model User",
                guide_topic="generate",
            )
        _sync_one(model_name, fields, dry_run, force, config)  # type: ignore[arg-type]

    if not dry_run:
        save_config(config)


def _sync_one(
    model_name: str,
    fields: Optional[str],
    dry_run: bool,
    force: bool,
    config: KairaConfig,
) -> None:
    """Sync a single model. Mutates *config*'s snapshot in place when applied."""
    try:
        validate_model_name(model_name)
    except ValueError as exc:
        smart_error(context=str(exc), typed=model_name, guide_topic="generate")

    base = Path.cwd()
    entry = next(
        (m for m in config.generated_models if m.get("name") == model_name), None
    )

    # ── Resolve current + target field sets ────────────────────────────────
    model_path = resolve_output_path("model", model_name, config, base)
    file_fields = _parse_model_fields(model_path) if model_path.exists() else None

    if entry is not None:
        old_fields = _snapshot_fields(entry)
        relations = _snapshot_relations(entry)
    elif file_fields is not None:
        # Older project without a snapshot — derive it from the model file.
        old_fields = file_fields
        relations = []
    else:
        smart_error(
            context=f"'{model_name}' is not a known model and has no model file to read.",
            fix_cmd=f'kaira generate model {model_name} --fields "name:str"',
            guide_topic="generate",
        )
        return  # unreachable — smart_error exits

    # Target = what the model file currently declares (source of truth if present),
    # otherwise the snapshot, with any inline --fields merged on top.
    target_fields = list(file_fields) if file_fields is not None else list(old_fields)
    if fields:
        try:
            target_fields = _merge_fields(target_fields, parse_fields(fields))
        except ValueError as exc:
            smart_error(context=str(exc), typed=fields, guide_topic="generate")

    old_names = {f.name for f in old_fields}
    target_names = {f.name for f in target_fields}
    added = sorted(target_names - old_names)
    removed = sorted(old_names - target_names)

    _print_plan(model_name, added, removed, config)

    if dry_run:
        return

    if not added and not removed and not fields:
        console.print(
            f"[{Theme.MUTED}]Nothing to sync for {model_name} — layers already match the snapshot.[/{Theme.MUTED}]"
        )
        return

    # ── Removed fields need a loud, explicit confirmation ──────────────────
    if removed:
        warn = sym("WARN")
        console.print(
            f"[{Theme.WARNING}]{warn} Removing field(s): {', '.join(removed)} — "
            f"data in those columns will no longer be modelled.[/{Theme.WARNING}]"
        )
        if not typed_confirmation(
            model_name,
            f"Confirm removal of {len(removed)} field(s) from {model_name}.",
            force=force,
        ):
            console.print(
                f"[{Theme.MUTED}]Sync aborted for {model_name}.[/{Theme.MUTED}]"
            )
            return

    # ── Cascade the mechanical layers ──────────────────────────────────────
    for layer in _CASCADE_LAYERS:
        content = generate_layer(layer, model_name, target_fields, relations, config)
        out_path = resolve_output_path(layer, model_name, config, base)
        result = write_with_check(out_path, content, force=force, non_interactive=False)
        ok, arrow = sym("OK"), sym("ARROW")
        if result == "written":
            console.print(
                f"  {ok} {layer}: [{Theme.PRIMARY}]{out_path}[/{Theme.PRIMARY}]"
            )
        else:
            console.print(f"  {arrow} {layer}: [{Theme.MUTED}]skipped[/{Theme.MUTED}]")

    # ── Flag the service layer (never auto-rewritten) ──────────────────────
    if added:
        _flag_service_layer(model_name, added, config, base)

    # ── Update the snapshot so the next diff is accurate ───────────────────
    register_model(
        config,
        model_name,
        [{"name": f.name, "type": f.raw_type} for f in target_fields],
        [{"type": r.relation_type, "target": r.target} for r in relations],
    )


def _print_plan(
    model_name: str, added: list[str], removed: list[str], config: KairaConfig
) -> None:
    """Render the per-layer sync plan panel."""
    changes = []
    if added:
        changes.append(f"[{Theme.SUCCESS}]+ {', '.join(added)}[/{Theme.SUCCESS}]")
    if removed:
        changes.append(f"[{Theme.ERROR}]- {', '.join(removed)}[/{Theme.ERROR}]")
    change_line = (
        "  ".join(changes)
        if changes
        else f"[{Theme.MUTED}]no field changes[/{Theme.MUTED}]"
    )

    is_document = config.db_type.lower() in _DOCUMENT_DB_TYPES
    repo_note = "skipped (unaffected)"
    body = "\n".join(
        [
            f"  [{Theme.MUTED}]Model:[/{Theme.MUTED}]      {model_name}   {change_line}",
            f"  [{Theme.MUTED}]Schema:[/{Theme.MUTED}]     regenerate (mirrors fields)",
            f"  [{Theme.MUTED}]Router:[/{Theme.MUTED}]     regenerate (re-point schema refs)",
            f"  [{Theme.MUTED}]Repository:[/{Theme.MUTED}] {repo_note}",
            f"  [{Theme.MUTED}]Service:[/{Theme.MUTED}]    flagged for manual review",
        ]
    )
    if not is_document:
        body += f'\n\n  [{Theme.MUTED}]Tip: run [/{Theme.MUTED}][{Theme.PRIMARY}]kaira migrate make "sync {model_name.lower()}"[/{Theme.PRIMARY}] [{Theme.MUTED}]after applying.[/{Theme.MUTED}]'
    panel(body, title=f"Sync Plan — {model_name}", border_style=Theme.BORDER_PRIMARY)


def _flag_service_layer(
    model_name: str, added: list[str], config: KairaConfig, base: Path
) -> None:
    """Warn that the service layer may need manual updates for new fields."""
    service_path = resolve_output_path("service", model_name, config, base)
    if not service_path.exists():
        return
    warn = sym("WARN")
    rel = (
        service_path.relative_to(base)
        if service_path.is_relative_to(base)
        else service_path
    )
    field_word = "field" if len(added) == 1 else "fields"
    console.print(
        f"\n[{Theme.WARNING}]{warn} {rel} — {len(added)} new {field_word} "
        f"({', '.join(added)}) may need handling.[/{Theme.WARNING}]\n"
        f"    [{Theme.MUTED}]Review manually: added to schema/model but not to any service method.[/{Theme.MUTED}]"
    )
