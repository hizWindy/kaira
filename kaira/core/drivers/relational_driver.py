"""Relational (SQL) Engine Driver for PostgreSQL, MySQL, and SQLite."""

from typing import Any

from kaira.core.drivers.base import BaseEngineDriver


class RelationalEngineDriver(BaseEngineDriver):
    """Engine driver for SQL relational databases."""

    @property
    def is_document_db(self) -> bool:
        return False

    @property
    def supports_alembic(self) -> bool:
        return True

    @property
    def supports_doc_migrations(self) -> bool:
        return False

    def get_model_template_name(self) -> str:
        return "model.py.j2"

    def get_repository_template_name(self) -> str:
        return "repository_async.py.j2"

    def get_seed_template_name(self) -> str:
        return "seed_model_sql.py.j2"

    def get_offline_fallback_url(self, db_name: str) -> str:
        clean_name = db_name.replace("-", "_").replace(".", "_")
        return f"sqlite+aiosqlite:///./{clean_name}_offline.db"

    def get_relation_snippet(
        self,
        source_model: str,
        target_model: str,
        relation_type: str,
        cascade: str = "",
        embedded: bool = False,
    ) -> dict[str, Any]:
        """Return SQLAlchemy relationship code snippets."""
        cascade_part = f', cascade="{cascade}"' if cascade else ""

        if relation_type == "has-many":
            field_code = f'    {target_model.lower()}s = relationship("{target_model}", back_populates="{source_model.lower()}"{cascade_part})'
        elif relation_type == "has-one":
            field_code = f'    {target_model.lower()} = relationship("{target_model}", back_populates="{source_model.lower()}", uselist=False{cascade_part})'
        elif relation_type == "many-to-many":
            field_code = f'    {target_model.lower()}s = relationship("{target_model}", secondary="{source_model.lower()}_{target_model.lower()}", back_populates="{source_model.lower()}s")'
        else:
            field_code = f'    {target_model.lower()} = relationship("{target_model}")'

        return {
            "imports": ["from sqlalchemy.orm import relationship"],
            "field_code": field_code,
            "type": "sqlalchemy",
        }
