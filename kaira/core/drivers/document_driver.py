"""Document (NoSQL) Engine Driver for MongoDB, Atlas, Firebase, etc."""

from typing import Dict, Any
from kaira.core.drivers.base import BaseEngineDriver


class DocumentEngineDriver(BaseEngineDriver):
    """Engine driver for NoSQL document stores."""

    @property
    def is_document_db(self) -> bool:
        return True

    @property
    def supports_alembic(self) -> bool:
        return False

    @property
    def supports_doc_migrations(self) -> bool:
        return True

    def get_model_template_name(self) -> str:
        return "model_mongodb.py.j2"

    def get_repository_template_name(self) -> str:
        return "repository_mongodb.py.j2"

    def get_seed_template_name(self) -> str:
        return "seed_model_doc.py.j2"

    def get_offline_fallback_url(self, db_name: str) -> str:
        clean_name = db_name.replace("-", "_").replace(".", "_")
        return f"mongodb://localhost:27017/{clean_name}_offline"

    def get_relation_snippet(
        self,
        source_model: str,
        target_model: str,
        relation_type: str,
        cascade: str = "",
        embedded: bool = False,
    ) -> Dict[str, Any]:
        """Return Beanie ODM document link or embedded snippet."""
        if embedded:
            if relation_type in ("has-many", "many-to-many"):
                field_code = (
                    f'    {target_model.lower()}s: list["{target_model}Schema"] = []'
                )
            else:
                field_code = (
                    f'    {target_model.lower()}: "{target_model}Schema" | None = None'
                )
            return {
                "imports": ["from typing import List, Optional"],
                "field_code": field_code,
                "type": "beanie_embedded",
            }

        # Linked document mode (Beanie Link[TargetModel])
        if relation_type in ("has-many", "many-to-many"):
            field_code = (
                f'    {target_model.lower()}s: list[Link["{target_model}"]] = []'
            )
        else:
            field_code = (
                f'    {target_model.lower()}: Link["{target_model}"] | None = None'
            )

        return {
            "imports": ["from beanie import Link"],
            "field_code": field_code,
            "type": "beanie_link",
        }
