"""SQLAlchemy model base abstraction layer."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class SQLAlchemyModel(DeclarativeBase):
    """Declarative Base class for SQLAlchemy ORM models in Kaira."""



Model = SQLAlchemyModel
