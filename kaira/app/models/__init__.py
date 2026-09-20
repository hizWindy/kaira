"""ORM abstraction layer — developers import from kaira.app.models or kaira directly."""

from __future__ import annotations

from typing import Any, Type

from kaira.app.models.mongo import Model as Document
from kaira.app.models.sqlalchemy import Model as SQLModel
from kaira.config import get_config


def _resolve_model_base() -> Type[Any]:
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


Model: Type[Any] = _resolve_model_base()

__all__ = ["Model", "SQLModel", "Document"]
