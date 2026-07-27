"""Base Engine Driver interface for Kaira database paradigms."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseEngineDriver(ABC):
    """Abstract base class defining database paradigm behaviors."""

    def __init__(self, db_type: str) -> None:
        self.db_type = db_type

    @property
    @abstractmethod
    def is_document_db(self) -> bool:
        """True if the database is a document/NoSQL store."""
        pass

    @property
    @abstractmethod
    def supports_alembic(self) -> bool:
        """True if the database paradigm uses Alembic migrations."""
        pass

    @property
    @abstractmethod
    def supports_doc_migrations(self) -> bool:
        """True if the database paradigm uses document migration scripts."""
        pass

    @abstractmethod
    def get_model_template_name(self) -> str:
        """Return the Jinja2 template file for model generation."""
        pass

    @abstractmethod
    def get_repository_template_name(self) -> str:
        """Return the Jinja2 template file for repository generation."""
        pass

    @abstractmethod
    def get_seed_template_name(self) -> str:
        """Return the Jinja2 template file for seed script generation."""
        pass

    @abstractmethod
    def get_offline_fallback_url(self, db_name: str) -> str:
        """Return the zero-config offline fallback URL/DSN."""
        pass

    @abstractmethod
    def get_relation_snippet(
        self,
        source_model: str,
        target_model: str,
        relation_type: str,
        cascade: str = "",
        embedded: bool = False,
    ) -> Dict[str, Any]:
        """Return snippet definitions for model relationship injection."""
        pass
