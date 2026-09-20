"""Tortoise ORM abstraction layer."""

from __future__ import annotations

from typing import Any

try:
    from tortoise.models import Model as _TortoiseModel

    class TortoiseModelBase(_TortoiseModel):
        pass

    Model = TortoiseModelBase
except ImportError:

    class TortoiseModelBase:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "tortoise-orm is not installed. Install with 'pip install tortoise-orm'"
            )

    Model = TortoiseModelBase  # type: ignore[misc]
