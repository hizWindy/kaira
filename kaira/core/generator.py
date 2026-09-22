"""Jinja2-based code generator for all 5 pipeline layers."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from kaira.config import (
    LAYER_SUFFIX,
    SERVER_MANAGED_FIELDS,
    TIER_LAYERS,
    KairaConfig,
    get_config,
)
from kaira.core.drivers import get_engine_driver
from kaira.core.parser import FieldDef, RelationDef, camel_to_snake, table_name

# ---------------------------------------------------------------------------
# Jinja2 Environment
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_template(template_name: str, context: dict) -> str:
    """Render a Jinja2 template by file name with the given context."""
    env = _get_jinja_env()
    template = env.get_template(template_name)
    return template.render(context)


# ---------------------------------------------------------------------------
# Template context builder
# ---------------------------------------------------------------------------


def _build_context(
    model_name: str,
    fields: list[FieldDef],
    relations: list[RelationDef],
    config: KairaConfig,
) -> dict:
    """Build the Jinja2 template rendering context."""
    snake = camel_to_snake(model_name)
    tbl = table_name(model_name)

    needs_datetime = any("datetime" in f.raw_type for f in fields)
    needs_optional = any(f.optional for f in fields)
    has_relations = bool(relations)

    # Embedded documents each need an import in every layer that names them.
    # Deduplicated and sorted so regenerating an unchanged model is a no-op diff.
    embedded_fields = [f for f in fields if f.is_embedded]
    embedded_imports = sorted({f.embedded_model for f in embedded_fields})

    # Categorize relations
    one_to_many = [r for r in relations if r.relation_type == "one-to-many"]
    many_to_one = [r for r in relations if r.relation_type == "many-to-one"]
    many_to_many = [r for r in relations if r.relation_type == "many-to-many"]

    return {
        # Model identity
        "model_name": model_name,
        "snake_name": snake,
        "table_name": tbl,
        # Fields
        "fields": fields,
        "needs_datetime": needs_datetime,
        "needs_optional": needs_optional,
        # Embedded (nested) documents
        "embedded_fields": embedded_fields,
        "embedded_imports": embedded_imports,
        "has_embedded": bool(embedded_fields),
        # Relations
        "relations": relations,
        "has_relations": has_relations,
        "one_to_many": one_to_many,
        "many_to_one": many_to_one,
        "many_to_many": many_to_many,
        # Directory layout from config
        "models_dir": config.models_dir,
        "repositories_dir": config.repositories_dir,
        "schemas_dir": config.schemas_dir,
        "services_dir": config.services_dir,
        "routers_dir": config.routers_dir,
        # Database/API version configurations
        "db_type": getattr(config, "db_type", "sqlite"),
        "api_version": getattr(config, "api_version", "v1"),
        "auth_type": getattr(config, "auth_type", "none"),
        "has_auth_guard": getattr(config, "auth_type", "none") != "none",
        # Helper: snake_case of a model name (callable from templates)
        "to_snake": camel_to_snake,
        # Server-managed fields excluded from Create schemas
        "server_managed_fields": SERVER_MANAGED_FIELDS,
    }


# ---------------------------------------------------------------------------
# Single-layer generation
# ---------------------------------------------------------------------------


def generate_layer(
    layer: str,
    model_name: str,
    fields: list[FieldDef],
    relations: list[RelationDef],
    config: KairaConfig | None = None,
) -> str:
    """Render and return the source code for a single pipeline layer.

    Parameters
    ----------
    layer:
        One of "model", "repository", "schema", "service", "router".
    model_name:
        PascalCase model name.
    fields:
        Parsed field definitions.
    relations:
        Parsed relation definitions.
    config:
        Kaira project config; loaded from file if *None*.
    """
    if config is None:
        config = get_config()

    env = _get_jinja_env()

    db_type = getattr(config, "db_type", "sqlite")
    driver = get_engine_driver(db_type)

    if layer == "model":
        template_name = driver.get_model_template_name()
    elif layer == "repository":
        template_name = driver.get_repository_template_name()
    else:
        template_name = f"{layer}.py.j2"

    try:
        template = env.get_template(template_name)
    except Exception as exc:
        raise FileNotFoundError(
            f"Template '{template_name}' not found in {TEMPLATES_DIR}"
        ) from exc

    ctx = _build_context(model_name, fields, relations, config)
    return template.render(**ctx)


def generate_embedded_model(
    model_name: str,
    fields: list[FieldDef],
    config: KairaConfig | None = None,
) -> str:
    """Render the source for an embedded (nested) document type.

    Embedded models are a single pydantic ``BaseModel`` — no repository,
    service or router, because they are values inside another document rather
    than a collection of their own.
    """
    if config is None:
        config = get_config()

    env = _get_jinja_env()
    template = env.get_template("embedded_model.py.j2")
    ctx = _build_context(model_name, fields, [], config)
    return template.render(**ctx)


# ---------------------------------------------------------------------------
# Multi-layer (full pipeline) generation
# ---------------------------------------------------------------------------


def generate_all(
    model_name: str,
    fields: list[FieldDef],
    relations: list[RelationDef],
    tier: str = "full",
    config: KairaConfig | None = None,
) -> dict[str, str]:
    """Render all layers for *model_name* and return a dict of layer → source.

    Parameters
    ----------
    tier:
        "simple" → model + schema + router only.
        "full"   → all 5 layers.
    """
    if config is None:
        config = get_config()

    layers = TIER_LAYERS.get(tier, TIER_LAYERS["full"])
    results: dict[str, str] = {}

    for layer in layers:
        results[layer] = generate_layer(layer, model_name, fields, relations, config)

    # Generate association tables for many-to-many relations
    if relations and any(r.relation_type == "many-to-many" for r in relations):
        env = _get_jinja_env()
        try:
            assoc_template = env.get_template("association.py.j2")
            ctx = _build_context(model_name, fields, relations, config)
            results["association"] = assoc_template.render(**ctx)
        except Exception:
            pass  # Association template optional

    return results


# ---------------------------------------------------------------------------
# File path resolution
# ---------------------------------------------------------------------------


def resolve_output_path(
    layer: str,
    model_name: str,
    config: KairaConfig | None = None,
    base_dir: Path | None = None,
) -> Path:
    """Return the output file path for a given layer and model.

    Example: layer='model', model_name='User' → ./models/user.py
    """
    if config is None:
        config = get_config()
    if base_dir is None:
        base_dir = Path.cwd()

    layer_dir = config.get_layer_dir(layer)
    suffix = LAYER_SUFFIX.get(layer, f"_{layer}")
    snake = camel_to_snake(model_name)
    filename = f"{snake}{suffix}.py"

    return base_dir / layer_dir / filename


def resolve_association_path(
    model_a: str,
    model_b: str,
    config: KairaConfig | None = None,
    base_dir: Path | None = None,
) -> Path:
    """Return the association table file path for a many-to-many relation."""
    if config is None:
        config = get_config()
    if base_dir is None:
        base_dir = Path.cwd()

    snake_a = camel_to_snake(model_a)
    snake_b = camel_to_snake(model_b)
    filename = f"{snake_a}_{snake_b}_association.py"
    return base_dir / config.models_dir / filename
