"""Authentication & Authorization abstraction module."""

from __future__ import annotations

from kaira.app.auth.api_key import ApiKey
from kaira.app.auth.jwt import JWT, JWTManager
from kaira.app.auth.oauth2 import OAuth2
from kaira.app.auth.password import hash_password, verify_password

__all__ = [
    "JWT",
    "JWTManager",
    "hash_password",
    "verify_password",
    "OAuth2",
    "ApiKey",
]
