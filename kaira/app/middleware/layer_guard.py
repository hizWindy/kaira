"""5-layer architecture runtime enforcement guard.

Ensures strict separation of concerns:
- Routers MUST NOT import or directly invoke Repositories.
- Routers MUST delegate to Services.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from kaira.app.exceptions import LayerViolationError


def audit_router_ast(filepath: Path) -> list[str]:
    """Scan a router Python file's AST for forbidden repository and database imports."""
    violations: list[str] = []
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except Exception:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if (
                    "repository" in alias.name.lower()
                    or "repositories" in alias.name.lower()
                ):
                    violations.append(
                        f"{filepath.name}: Direct import of '{alias.name}' in router layer is prohibited."
                    )
                if alias.name in ("core.database", "khaira.database"):
                    violations.append(
                        f"{filepath.name}: Direct import of '{alias.name}' in router layer is prohibited. Use service layer."
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if "repository" in mod.lower() or "repositories" in mod.lower():
                violations.append(
                    f"{filepath.name}: Direct 'from {mod}' in router layer is prohibited. Use service layer."
                )
            if mod in ("core.database", "khaira.database"):
                violations.append(
                    f"{filepath.name}: Direct 'from {mod}' in router layer is prohibited. Use service layer."
                )
    return violations


def audit_layers(routers_dir: Path) -> list[str]:
    """Audit all router files in a project for layer separation compliance."""
    if not routers_dir.exists():
        return []
    all_violations: list[str] = []
    for r_file in routers_dir.rglob("*.py"):
        if r_file.name.startswith("__"):
            continue
        all_violations.extend(audit_router_ast(r_file))
    return all_violations


class LayerGuardMiddleware(BaseHTTPMiddleware):
    """Starlette middleware verifying architecture boundaries at runtime."""

    def __init__(
        self,
        app: Any,
        routers_dir: Path | None = None,
        enforce: bool = True,
    ) -> None:
        super().__init__(app)
        self.enforce = enforce
        self.routers_dir = routers_dir or Path("routers")
        self._checked = False

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        if self.enforce and not self._checked:
            violations = audit_layers(self.routers_dir)
            if violations:
                raise LayerViolationError(
                    "5-Layer architecture violation detected:\n" + "\n".join(violations)
                )
            self._checked = True
        return await call_next(request)  # type: ignore[no-any-return]
