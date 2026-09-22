"""Authentication provider for Khaira Framework applications."""

from __future__ import annotations

import os
from typing import Any

from kaira.app.auth.jwt import JWTManager
from kaira.app.auth.password import hash_password, verify_password
from kaira.app.providers.base import KairaProvider


class AuthProvider(KairaProvider):
    """Authentication provider managing JWT tokens and password hashing."""

    name: str = "auth"

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 60,
    ) -> None:
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY", "default-insecure-secret-key-32chars!"
        )
        self.algorithm = algorithm
        self.jwt = JWTManager(secret_key=self.secret_key, algorithm=self.algorithm)
        self.access_token_expire_minutes = access_token_expire_minutes

    def register(self, app: Any) -> None:
        """Register auth utilities on app state."""
        app.state.auth = self

    def hash_password(self, password: str) -> str:
        return hash_password(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        return verify_password(password, hashed)

    def create_token(
        self, payload: dict[str, Any], expires_minutes: int | None = None
    ) -> str:
        return self.jwt.create_token(
            payload,
            expires_minutes=expires_minutes or self.access_token_expire_minutes,
        )

    def verify_token(self, token: str) -> dict[str, Any] | None:
        return self.jwt.verify_token(token)
