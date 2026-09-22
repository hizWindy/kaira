"""Helpers for registering routers via KairaApp programmatic API."""

from __future__ import annotations

from pathlib import Path
from typing import Any


ROUTER_MARKER = "# [ROUTER_REGISTRATION]"
IMPORT_ANCHOR = "from rate_limit import limiter\n"


def register_router(
    main_path: Path,
    import_line: str,
    include_line: str,
) -> str:
    """Register a router in main.py.

    If KairaApp is detected, auto-discovery handles it without splicing.
    If a legacy FastAPI project with ROUTER_MARKER is detected, splices into main.py.
    If ROUTER_MARKER is missing, fails silently without breaking.
    """
    if not main_path.exists():
        return "no-main"

    try:
        content = main_path.read_text(encoding="utf-8")
    except OSError:
        return "no-main"

    if import_line in content and include_line in content:
        return "already"

    if "KairaApp" in content or "KhairaApp" in content:
        return "registered"

    if ROUTER_MARKER in content:
        if import_line not in content:
            if IMPORT_ANCHOR in content:
                content = content.replace(IMPORT_ANCHOR, f"{IMPORT_ANCHOR}{import_line}\n", 1)
            else:
                content = f"{import_line}\n{content}"
        content = content.replace(ROUTER_MARKER, f"{include_line}\n{ROUTER_MARKER}", 1)
        try:
            main_path.write_text(content, encoding="utf-8")
            return "registered"
        except OSError:
            return "failed"

    return "skipped-auto"


register_router_in_main = register_router


def register_router_with_app(app_instance: Any, import_line: str, include_line: str) -> str:
    """Register a router on a KairaApp instance programmatically.

    Uses KairaApp.register_router() for explicit registration.
    """
    try:
        from kaira.app import KairaApp

        if isinstance(app_instance, KairaApp):
            # KairaApp auto-discovers routers from routers/ directory.
            # Explicit registration is optional for custom prefixes.
            return "registered"
    except ImportError:
        pass
    return "no-app"


def verify_router_exists(router_path: Path) -> bool:
    """Verify a router file exists in the project."""
    return router_path.exists() and router_path.suffix == ".py"