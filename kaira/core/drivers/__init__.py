"""Engine Driver factory and exports."""

from kaira.core.drivers.base import BaseEngineDriver
from kaira.core.drivers.relational_driver import RelationalEngineDriver
from kaira.core.drivers.document_driver import DocumentEngineDriver

_DOCUMENT_DB_TYPES = {"mongodb", "atlas", "firebase", "firestore"}


def get_engine_driver(db_type: str = "sqlite") -> BaseEngineDriver:
    """Return the appropriate BaseEngineDriver instance for a given database type."""
    normalized = (db_type or "sqlite").lower().strip()
    if normalized in _DOCUMENT_DB_TYPES:
        return DocumentEngineDriver(normalized)
    return RelationalEngineDriver(normalized)


__all__ = [
    "BaseEngineDriver",
    "RelationalEngineDriver",
    "DocumentEngineDriver",
    "get_engine_driver",
]
