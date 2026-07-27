"""Field and relation parser for Kaira model definitions."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Optional

from kaira.config import SQLALCHEMY_TYPE_MAP, PYTHON_TYPE_MAP


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


def normalize_ast_type(raw_type: str) -> Optional[str]:
    """Normalize raw type annotations (e.g. 'str | None', 'typing.Optional[int]') to canonical forms."""
    raw = raw_type.strip().strip('"').strip("'")
    if raw.startswith("typing."):
        raw = raw[7:]
    raw = raw.replace("typing.", "")

    if " | None" in raw or "None | " in raw:
        clean = raw.replace(" | None", "").replace("None | ", "").strip()
        if clean in _VALID_BASE_TYPES:
            return f"Optional[{clean}]"
    if raw.startswith("Union[") and "None" in raw:
        for b in _VALID_BASE_TYPES:
            if b in raw:
                return f"Optional[{b}]"
    if raw in _VALID_BASE_TYPES:
        return raw
    if raw.startswith("Optional["):
        inner = raw[9:-1].strip()
        if inner in _VALID_BASE_TYPES:
            return f"Optional[{inner}]"
    return None


def infer_column_type(value: Optional[ast.expr]) -> Optional[str]:
    """Infer field type from Column(...) or mapped_column(...) AST call arguments."""
    if value is None or not isinstance(value, ast.Call):
        return None

    func = value.func
    fname = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr
        if isinstance(func, ast.Attribute)
        else ""
    )
    if fname not in ("Column", "mapped_column"):
        return None

    if not value.args:
        return None

    arg = value.args[0]
    col_type_name = ""
    if isinstance(arg, ast.Call):
        col_type_name = (
            arg.func.id
            if isinstance(arg.func, ast.Name)
            else arg.func.attr
            if isinstance(arg.func, ast.Attribute)
            else ""
        )
    elif isinstance(arg, ast.Name):
        col_type_name = arg.id
    elif isinstance(arg, ast.Attribute):
        col_type_name = arg.attr

    mapping = {
        "String": "str",
        "Text": "str",
        "VARCHAR": "str",
        "Integer": "int",
        "BigInteger": "int",
        "SmallInteger": "int",
        "Float": "float",
        "Numeric": "float",
        "Boolean": "bool",
        "DateTime": "datetime",
        "Date": "datetime",
        "Timestamp": "datetime",
    }
    base = mapping.get(col_type_name)
    if not base:
        return None

    nullable = False
    for kw in value.keywords:
        if (
            kw.arg == "nullable"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is True
        ):
            nullable = True
            break

    return f"Optional[{base}]" if nullable else base


def _normalize_type(raw: str) -> str:
    """Normalize a raw type string to a canonical form."""
    raw_str = raw.strip()
    m = _OPTIONAL_RE.match(raw_str)
    if m:
        inner = m.group(1).strip()
        if inner not in _VALID_BASE_TYPES:
            raise ValueError(
                f"Unsupported Optional inner type '{inner}'. "
                f"Supported: {sorted(_VALID_BASE_TYPES)}"
            )
        return f"Optional[{inner}]"
    norm = normalize_ast_type(raw_str)
    if norm is None:
        raise ValueError(
            f"Unsupported field type '{raw_str}'. "
            f"Supported: {sorted(_VALID_BASE_TYPES)} or Optional[<type>]"
        )
    return norm


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
