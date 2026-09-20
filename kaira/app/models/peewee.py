"""Peewee ORM abstraction layer."""

from __future__ import annotations

from typing import Any

try:
    from peewee import Model as _PeeweeModel

    class PeeweeModelBase(_PeeweeModel):
        pass

    Model = PeeweeModelBase
except ImportError:

    class PeeweeModelBase:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "peewee is not installed. Install with 'pip install peewee'"
            )

    Model = PeeweeModelBase  # type: ignore[misc]
