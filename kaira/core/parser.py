"""Field and relation parser for Kaira model definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from kaira.config import SUPPORTED_FIELD_TYPES, SQLALCHEMY_TYPE_MAP, PYTHON_TYPE_MAP


@dataclass
class FieldDef:
    """Represents a single model field."""

    name: str
    raw_type: str  # e.g. "str", "Optional[int]"
    optional: bool = False
    sqlalchemy_type: str = ""
    python_type: str = ""

    def __post_init__(self) -> None:
        self.optional = self.raw_type.startswith("Optional[")
        self.sqlalchemy_type = SQLALCHEMY_TYPE_MAP.get(self.raw_type, "String")
        self.python_type = PYTHON_TYPE_MAP.get(self.raw_type, self.raw_type)


@dataclass
class RelationDef:
    """Represents a relationship between models."""

    relation_type: str  # "one-to-many", "many-to-one", "many-to-many"
    target: str  # Target model name (PascalCase)
    cascade: Optional[str] = None
    back_populates: Optional[str] = None

    def __post_init__(self) -> None:
        if self.back_populates is None:
            # auto-derive back_populates name
            if self.relation_type in ("one-to-many", "many-to-many"):
                self.back_populates = camel_to_snake(self.target) + "s"
            else:
                self.back_populates = camel_to_snake(self.target)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASCAL_CASE_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")


def validate_model_name(name: str) -> str:
    """Validate that *name* is PascalCase. Returns the name or raises ValueError."""
    if not PASCAL_CASE_RE.match(name):
        raise ValueError(
            f"Model name '{name}' must be PascalCase (e.g. UserProfile, BlogPost)."
        )
    return name


def camel_to_snake(name: str) -> str:
    """Convert PascalCase / CamelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def pluralize(name: str) -> str:
    """Very simple pluralizer for table names."""
    if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
        return name[:-1] + "ies"
    if name.endswith(("s", "sh", "ch", "x", "z")):
        return name + "es"
    return name + "s"


def table_name(model_name: str) -> str:
    """Return a snake_case plural table name from a PascalCase model name."""
    return pluralize(camel_to_snake(model_name))


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------

_OPTIONAL_RE = re.compile(r"^Optional\[(.+)\]$")
_VALID_BASE_TYPES = {"str", "int", "float", "bool", "datetime"}


def _normalize_type(raw: str) -> str:
    """Normalize a raw type string to a canonical form."""
    raw = raw.strip()
    m = _OPTIONAL_RE.match(raw)
    if m:
        inner = m.group(1).strip()
        if inner not in _VALID_BASE_TYPES:
            raise ValueError(
                f"Unsupported Optional inner type '{inner}'. "
                f"Supported: {sorted(_VALID_BASE_TYPES)}"
            )
        return f"Optional[{inner}]"
    if raw not in _VALID_BASE_TYPES:
        raise ValueError(
            f"Unsupported field type '{raw}'. "
            f"Supported: {sorted(_VALID_BASE_TYPES)} or Optional[<type>]"
        )
    return raw


def parse_fields(fields_str: str) -> list[FieldDef]:
    """Parse a fields string like 'name:str, age:int, email:Optional[str]'.

    Returns a list of :class:`FieldDef` instances.
    Raises :class:`ValueError` on invalid types or malformed tokens.
    """
    if not fields_str or not fields_str.strip():
        return []

    results: list[FieldDef] = []
    tokens = [t.strip() for t in fields_str.split(",") if t.strip()]

    for token in tokens:
        if ":" not in token:
            raise ValueError(
                f"Invalid field definition '{token}'. Expected format: name:type"
            )
        parts = token.split(":", 1)
        fname = parts[0].strip()
        ftype = parts[1].strip()

        if not re.match(r"^[a-z_][a-z0-9_]*$", fname):
            raise ValueError(
                f"Field name '{fname}' must be lowercase snake_case."
            )

        normalized = _normalize_type(ftype)
        results.append(FieldDef(name=fname, raw_type=normalized))

    return results


# ---------------------------------------------------------------------------
# Relation parsing
# ---------------------------------------------------------------------------

VALID_RELATION_TYPES = {"one-to-many", "many-to-one", "many-to-many"}


def parse_relation(
    relation_type: str,
    target: str,
    cascade: Optional[str] = None,
) -> RelationDef:
    """Create a :class:`RelationDef` from raw CLI inputs."""
    if relation_type not in VALID_RELATION_TYPES:
        raise ValueError(
            f"Unknown relation type '{relation_type}'. "
            f"Supported: {sorted(VALID_RELATION_TYPES)}"
        )
    validate_model_name(target)
    return RelationDef(relation_type=relation_type, target=target, cascade=cascade)


def parse_relations_from_json(relations_data: list[dict]) -> list[RelationDef]:
    """Parse relation dicts as found in a bulk JSON file."""
    results = []
    for r in relations_data:
        rtype = r.get("type", "")
        target = r.get("target", "")
        cascade = r.get("cascade")
        results.append(parse_relation(rtype, target, cascade))
    return results
