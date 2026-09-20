"""Cache provider for Khaira Framework applications (Redis / In-memory)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

from kaira.app.providers.base import KairaProvider


class CacheProvider(KairaProvider):
    """Caching provider wrapping Redis with an in-memory fallback."""

    name: str = "cache"

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = None
        self._memory_cache: Dict[str, Tuple[str, Optional[float]]] = {}
        self._use_redis = False

    def register(self, app: Any) -> None:
        """Attach cache provider to app state."""
        app.state.cache = self

    async def startup(self) -> None:
        """Initialize Redis connection if library is available and reachable."""
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(self.redis_url)
            await client.ping()
            self._client = client
            self._use_redis = True
        except Exception:
            self._use_redis = False

    async def shutdown(self) -> None:
        """Close connection pools."""
        if self._client and self._use_redis:
            await self._client.aclose()

    async def get(self, key: str) -> Optional[str]:
        """Retrieve a cached string value."""
        if self._use_redis and self._client:
            val = await self._client.get(key)
            return val.decode("utf-8") if isinstance(val, bytes) else val

        # In-memory fallback
        if key in self._memory_cache:
            val, expiry = self._memory_cache[key]
            if expiry is None or expiry > time.time():
                return val
            del self._memory_cache[key]
        return None

    async def set(self, key: str, value: str, expire: Optional[int] = 3600) -> None:
        """Set a cached key with an optional TTL in seconds."""
        if self._use_redis and self._client:
            await self._client.set(key, value, ex=expire)
            return

        expiry_ts = time.time() + expire if expire else None
        self._memory_cache[key] = (value, expiry_ts)

    async def delete(self, key: str) -> None:
        """Remove a cached key."""
        if self._use_redis and self._client:
            await self._client.delete(key)
        else:
            self._memory_cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all keys in cache."""
        if self._use_redis and self._client:
            await self._client.flushdb()
        else:
            self._memory_cache.clear()
