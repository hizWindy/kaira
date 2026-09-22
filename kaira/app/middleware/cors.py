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
    eff_origins = origins or ["http://localhost:3000", "http://localhost:8000"]
    # Per CORS standard, wildcard '*' is forbidden when allow_credentials=True
    if "*" in eff_origins and allow_credentials:
        allow_credentials = False

    return CORSMiddleware, {
        "allow_origins": eff_origins,
        "allow_credentials": allow_credentials,
        "allow_methods": allow_methods or ["*"],
        "allow_headers": allow_headers or ["*"],
    }
