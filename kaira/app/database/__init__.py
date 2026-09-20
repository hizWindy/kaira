"""Database abstraction module for Khaira framework."""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Optional

try:
    from sqlalchemy.ext.asyncio import AsyncSession
except ImportError:
    AsyncSession = Any  # type: ignore[misc,assignment]

try:
    from sqlalchemy.orm import DeclarativeBase, Session, declarative_base

    class Base(DeclarativeBase):
        """Shared declarative base for ORM models."""

except ImportError:
    Session = Any  # type: ignore[misc,assignment]
    DeclarativeBase = Any  # type: ignore[misc,assignment]
    declarative_base = Any  # type: ignore[misc,assignment]

    class Base:  # type: ignore[no-redef]
        pass


class Database:
    """Database connection and session helper."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./app.db"

    def get_dsn(self) -> str:
        return self.dsn


async def get_db() -> AsyncGenerator[Any, None]:
    """Default database dependency placeholder.

    In a generated project, this delegates to core.database.get_db when available.
    """
    try:
        from core.database import get_db as _core_get_db

        async for session in _core_get_db():
            yield session
    except ImportError:
        yield None


__all__ = [
    "Base",
    "DeclarativeBase",
    "declarative_base",
    "Database",
    "AsyncSession",
    "Session",
    "get_db",
]
