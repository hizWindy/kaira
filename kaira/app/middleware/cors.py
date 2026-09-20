"""CORS middleware configuration for KairaApp."""

from __future__ import annotations

from typing import List, Optional
from starlette.middleware.cors import CORSMiddleware


def create_cors_middleware(
    origins: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
) -> tuple[type[CORSMiddleware], dict]:
    """Return middleware class and kwargs for app.add_middleware."""
    return CORSMiddleware, {
        "allow_origins": origins or ["*"],
        "allow_credentials": allow_credentials,
        "allow_methods": allow_methods or ["*"],
        "allow_headers": allow_headers or ["*"],
    }
