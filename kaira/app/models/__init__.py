"""ORM abstraction layer — developers import from khaira.models or kaira.models."""

from __future__ import annotations

from typing import Any, Type

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kaira.app.models.mongo import Model as Document
from kaira.app.models.sqlalchemy import Model as SQLModel
from kaira.config import get_config


def _resolve_model_base() -> type[Any]:
    try:
        cfg = get_config()
        orm = getattr(cfg, "orm", "sqlalchemy").lower()
        db_type = getattr(cfg, "db_type", "sqlite").lower()
    except Exception:
        orm = "sqlalchemy"
        db_type = "sqlite"

    if db_type == "mongodb" or orm == "beanie":
        return Document
    elif orm == "sqlmodel":
        from kaira.app.models.sqlmodel import Model as SQLModelBase

        return SQLModelBase
    elif orm == "peewee":
        from kaira.app.models.peewee import Model as PeeweeModel

        return PeeweeModel
    elif orm == "tortoise":
        from kaira.app.models.tortoise import Model as TortoiseModel

        return TortoiseModel
    else:
        return SQLModel


Model: type[Any] = _resolve_model_base()
BaseModel = Model

__all__ = [
    # Base models
    "Model",
    "BaseModel",
    "SQLModel",
    "Document",
    # SQLAlchemy types
    "Column",
    "Integer",
    "String",
    "Float",
    "Boolean",
    "DateTime",
    "Text",
    "ForeignKey",
    "Index",
    "Enum",
    "JSON",
    "Table",
    # Mapped & Query constructs
    "relationship",
    "Mapped",
    "mapped_column",
    "select",
]
