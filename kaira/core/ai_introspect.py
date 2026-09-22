"""AST-based introspection engine for converting Kaira services into AI Agent Skills."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParameterMeta:
    name: str
    type_annotation: str = "Any"
    default_value: str | None = None


@dataclass
class MethodMeta:
    name: str
    docstring: str = ""
    parameters: list[ParameterMeta] = field(default_factory=list)
    return_type: str = "Any"
    is_async: bool = True


@dataclass
class ServiceMeta:
    class_name: str
    file_path: Path
    methods: list[MethodMeta] = field(default_factory=list)


def _format_annotation(node: ast.AST | None) -> str:
    """Safely convert an AST annotation node to a Python type string."""
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        return "Any"


def introspect_service_file(file_path: Path) -> list[ServiceMeta]:
    """Parse a Python service file and extract classes and callable domain methods."""
    if not file_path.exists() or file_path.suffix != ".py":
        return []

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except Exception:
        return []

    services: list[ServiceMeta] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_meta = ServiceMeta(class_name=node.name, file_path=file_path)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Exclude private methods and dunder methods
                    if item.name.startswith("_"):
                        continue

                    docstring = (
                        ast.get_docstring(item)
                        or f"Execute {item.name} on {node.name}."
                    )
                    is_async = isinstance(item, ast.AsyncFunctionDef)
                    return_type = _format_annotation(item.returns)

                    params: list[ParameterMeta] = []
                    # Process args, skipping 'self' or 'cls'
                    for arg in item.args.args:
                        if arg.arg in ("self", "cls"):
                            continue
                        ann = _format_annotation(arg.annotation)
                        params.append(ParameterMeta(name=arg.arg, type_annotation=ann))

                    class_meta.methods.append(
                        MethodMeta(
                            name=item.name,
                            docstring=docstring.strip(),
                            parameters=params,
                            return_type=return_type,
                            is_async=is_async,
                        )
                    )

            if class_meta.methods:
                services.append(class_meta)

    return services


def introspect_all_services(services_dir: Path) -> list[ServiceMeta]:
    """Scan the services directory and return metadata for all discovered domain services."""
    if not services_dir.exists() or not services_dir.is_dir():
        return []

    discovered: list[ServiceMeta] = []
    for file in sorted(services_dir.glob("*.py")):
        if file.name.startswith("__"):
            continue
        discovered.extend(introspect_service_file(file))

    return discovered
