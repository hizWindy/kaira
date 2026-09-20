"""API Key abstraction using cryptographically secure tokens."""

from __future__ import annotations

import hashlib
import secrets


class ApiKey:
    """Utilities for generating and hashing API Keys."""

    @staticmethod
    def generate(prefix: str = "kaira", length: int = 32) -> str:
        """Generate a random URL-safe API key."""
        token = secrets.token_urlsafe(length)
        return f"{prefix}_{token}"

    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key using SHA-256 for secure database storage."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    @staticmethod
    def verify(raw_key: str, hashed_key: str) -> bool:
        """Constant-time comparison between raw and stored hashed key."""
        candidate = ApiKey.hash_key(raw_key)
        return secrets.compare_digest(candidate, hashed_key)
