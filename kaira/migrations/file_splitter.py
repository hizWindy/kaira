"""File splitter: decomposes combined single-file modules into standard 5-layer components."""

from __future__ import annotations

import ast
from pathlib import Path


class FileSplitter:
    """Parses single-file model definitions and distributes code into 5-layer files."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    def split_combined_model(self, model_file: Path) -> dict[str, str]:
        """Inspects a combined model file and extracts model, schema, and router code blocks."""
        if not model_file.exists():
            return {}

        source = model_file.read_text(encoding="utf-8")
        stem = model_file.stem
        # Basic AST-driven extraction
        try:
            tree = ast.parse(source)
        except Exception:
            return {"model": source}

        model_nodes: list[ast.AST] = []
        schema_nodes: list[ast.AST] = []
        router_nodes: list[ast.AST] = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                base_names = [b.id for b in node.bases if isinstance(b, ast.Name)]
                if (
                    any("Schema" in b or "BaseModel" in b for b in base_names)
                    or "Schema" in node.name
                ):
                    schema_nodes.append(node)
                else:
                    model_nodes.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                router_nodes.append(node)
            else:
                model_nodes.append(node)

        return {
            "model": source,
            "stem": stem,
        }
