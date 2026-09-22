"""MongoDB / Beanie Document abstraction layer."""

from __future__ import annotations

from typing import Any

try:
    from beanie import Document

    class MongoDocument(Document):
        """Beanie Document base class for Kaira."""


    Model = MongoDocument
except ImportError:

    class MongoDocument:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "beanie is not installed. Install with 'pip install beanie motor'"
            )

    Model = MongoDocument  # type: ignore[misc]
