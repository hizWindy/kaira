"""Helpers for wiring generated routers into the project's ``main.py``."""

from __future__ import annotations

from pathlib import Path

ROUTER_MARKER = "# [ROUTER_REGISTRATION]"
IMPORT_ANCHOR = "from rate_limit import limiter\n"


def register_router_in_main(main_path: Path, import_line: str, include_line: str) -> str:
    """Splice a router import and ``include_router`` call into ``main.py``.

    The include line is inserted just above the ``# [ROUTER_REGISTRATION]``
    marker written by the Phase 3 main template. Safe to call repeatedly.

    Returns one of ``"registered"``, ``"already"``, ``"no-main"`` or
    ``"no-marker"`` so callers can decide what to report.
    """
    if not main_path.exists():
        return "no-main"

    try:
        content = main_path.read_text(encoding="utf-8")
    except OSError:
        return "no-main"

    if ROUTER_MARKER not in content:
        return "no-marker"

    if import_line in content and include_line in content:
        return "already"

    if import_line not in content:
        if IMPORT_ANCHOR in content:
            content = content.replace(IMPORT_ANCHOR, f"{IMPORT_ANCHOR}{import_line}\n", 1)
        else:
            content = f"{import_line}\n{content}"

    if include_line not in content:
        content = content.replace(ROUTER_MARKER, f"{include_line}\n{ROUTER_MARKER}", 1)

    main_path.write_text(content, encoding="utf-8")
    return "registered"
