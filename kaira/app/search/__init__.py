"""Search engine abstraction module (Meilisearch / Elasticsearch)."""

from __future__ import annotations

from typing import Any, List


class Search:
    """Full-text search abstraction."""

    def __init__(self, provider: str = "meilisearch") -> None:
        self.provider = provider

    async def search(self, index: str, query: str, limit: int = 20) -> List[Any]:
        return []


__all__ = ["Search"]
