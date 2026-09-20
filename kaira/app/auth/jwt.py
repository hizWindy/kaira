"""JWT token abstraction wrapping PyJWT and python-jose."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    import jwt  # PyJWT

    _HAS_PYJWT = True
except ImportError:
    _HAS_PYJWT = False

try:
    from jose import jwt as jose_jwt  # python-jose

    _HAS_JOSE = True
except ImportError:
    _HAS_JOSE = False


class JWTManager:
    """Manages JWT creation and validation."""

    def __init__(
        self, secret_key: Optional[str] = None, algorithm: str = "HS256"
    ) -> None:
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY", "default-32-char-secret-key-kaira!"
        )
        self.algorithm = algorithm

    def create_token(self, payload: Dict[str, Any], expires_minutes: int = 60) -> str:
        """Encode a dictionary payload into a signed JWT."""
        to_encode = payload.copy()
        exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        to_encode["exp"] = exp

        if _HAS_PYJWT:
            return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)  # type: ignore[no-any-return]
        if _HAS_JOSE:
            return jose_jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)  # type: ignore[no-any-return]

        raise RuntimeError("No JWT library installed. Install PyJWT or python-jose.")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and verify a JWT, returning payload or None if invalid/expired."""
        try:
            if _HAS_PYJWT:
                return jwt.decode(token, self.secret_key, algorithms=[self.algorithm])  # type: ignore[no-any-return]
            if _HAS_JOSE:
                return jose_jwt.decode(
                    token, self.secret_key, algorithms=[self.algorithm]
                )  # type: ignore[no-any-return]
        except Exception:
            return None
        return None


class JWT(JWTManager):
    """Framework-managed JWT alias."""

    pass
