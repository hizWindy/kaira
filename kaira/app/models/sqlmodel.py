"""SQLModel abstraction layer."""

from __future__ import annotations

from typing import Any

try:
    from sqlmodel import SQLModel as _SQLModel

    class SQLModelBase(_SQLModel):
        """SQLModel base class for Kaira."""


    Model = SQLModelBase
except ImportError:

    class SQLModelBase:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "sqlmodel is not installed. Install with 'pip install sqlmodel'"
            )

    Model = SQLModelBase  # type: ignore[misc]
