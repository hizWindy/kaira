"""Generates upgraded project files, middleware, and documentation templates."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class FileWriter:
    """Writes files and documentation required for higher framework tiers."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def write_standard_docs(self, project_name: str) -> list[str]:
        """Generate docs/ markdown documentation files."""
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        ctx = {"project_name": project_name}
        created: list[str] = []

        doc_templates = [
            ("index.md", "docs/index.md.j2"),
            ("architecture.md", "docs/architecture.md.j2"),
            ("api-reference.md", "docs/api-reference.md.j2"),
            ("setup.md", "docs/setup.md.j2"),
            ("migration-guide.md", "docs/migration-guide.md.j2"),
        ]

        for dest_name, tmpl_name in doc_templates:
            dest = docs_dir / dest_name
            if not dest.exists():
                try:
                    tmpl = self.env.get_template(tmpl_name)
                    dest.write_text(tmpl.render(**ctx), encoding="utf-8")
                except Exception:
                    # Fallback if template missing
                    dest.write_text(
                        f"# {dest_name.replace('.md', '').title()}\n\nDocumentation for {project_name}.\n",
                        encoding="utf-8",
                    )
                created.append(str(dest.relative_to(self.root)))

        return created

    def ensure_layer_directories(self) -> None:
        """Ensure all 5 standard layer directories exist."""
        for layer in ["models", "schemas", "services", "repositories", "routers"]:
            d = self.root / layer
            d.mkdir(parents=True, exist_ok=True)
            init_py = d / "__init__.py"
            if not init_py.exists():
                init_py.touch()
