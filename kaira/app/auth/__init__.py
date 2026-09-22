"""Authentication & Authorization abstraction module for Khaira framework."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
    SecurityScopes,
)

from kaira.app.auth.api_key import ApiKey
from kaira.app.auth.jwt import JWT, JWTManager
from kaira.app.auth.oauth2 import OAuth2
from kaira.app.auth.password import hash_password, verify_password


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token."""
    mgr = JWTManager()
    expires_minutes = int(expires_delta.total_seconds() / 60) if expires_delta else 60
    return mgr.create_token(data, expires_minutes=expires_minutes)


async def get_current_user(*args: Any, **kwargs: Any) -> Any:
    """Dependency placeholder for get_current_user; delegates to auth.dependencies if available."""
    try:
        from auth.dependencies import (
            get_current_user as _auth_get_current_user,  # type: ignore[import-not-found]
        )
        return await _auth_get_current_user(*args, **kwargs)
    except Exception:
        return None


__all__ = [
    # Core primitives & helpers
    "create_access_token",
    "get_current_user",
    "JWT",
    "JWTManager",
    "hash_password",
    "verify_password",
    "OAuth2",
    "ApiKey",
    # FastAPI security helpers
    "OAuth2PasswordBearer",
    "OAuth2PasswordRequestForm",
    "SecurityScopes",
    "HTTPBearer",
    "HTTPAuthorizationCredentials",
    "APIKeyHeader",
    "APIKeyQuery",
    "APIKeyCookie",
]
