"""Database abstraction module."""

from __future__ import annotations

import os
from typing import Optional


class Database:
    """Database connection and session helper."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        self.dsn = dsn or os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./app.db"

    def get_dsn(self) -> str:
        return self.dsn


__all__ = ["Database"]
