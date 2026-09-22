"""Khaira — Automated FastAPI Scaffolding CLI and Framework Runtime."""

from __future__ import annotations

import importlib
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any, List, Optional, Set

__version__ = "0.2.5"
__author__ = "Kaira"
__description__ = "Automated FastAPI scaffolding CLI and framework runtime."
__homepage__ = "https://github.com/hizWindy/kaira"

from kaira.app.database import AsyncSession, Base, Database, Session
from kaira.app.http import (
    APIRouter,
    Depends,
    HTTPException,
    Limiter,
    Query,
    Request,
    Router,
    get_remote_address,
    limiter,
    status,
)
from kaira.app.kaira_app import KairaApp
from kaira.app.models import Document, Model
from kaira.app.providers.base import KairaProvider
from kaira.app.schemas import Schema
from kaira.config import KairaConfig, get_config

RateLimiter = limiter
KhairaApp = KairaApp
KhairaProvider = KairaProvider
KhairaConfig = KairaConfig


class _ForwardLoader:
    def __init__(self, mod: ModuleType) -> None:
        self.mod = mod

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        return self.mod

    def exec_module(self, module: ModuleType) -> None:
        pass

    def get_code(self, fullname: str) -> Any:
        file = getattr(self.mod, "__file__", None)
        if file:
            try:
                from pathlib import Path

                return compile(Path(file).read_text(encoding="utf-8"), file, "exec")
            except Exception:
                pass
        return None

    def get_source(self, fullname: str) -> str | None:
        file = getattr(self.mod, "__file__", None)
        if file:
            try:
                from pathlib import Path

                return Path(file).read_text(encoding="utf-8")
            except Exception:
                pass
        return None

    def is_package(self, fullname: str) -> bool:
        return hasattr(self.mod, "__path__")


_in_progress: set[str] = set()

_APP_SUBMODULES = {
    "http",
    "auth",
    "schemas",
    "models",
    "database",
    "cache",
    "rate_limit",
    "task",
    "ai",
    "logging",
    "tracing",
    "security",
    "middleware",
    "export",
    "storage",
    "notify",
    "analytics",
    "search",
    "container",
    "lifecycle",
    "dep",
    "exceptions",
}


class _KairaSubmoduleFinder:
    """Dynamically route any kaira.<app_submodule> or khaira.<submodule> to kaira.app.<submodule>."""

    @classmethod
    def find_spec(
        cls,
        fullname: str,
        path: list[str] | None = None,
        target: ModuleType | None = None,
    ) -> Any:
        if fullname in _in_progress:
            return None

        # Let physical __main__.py files execute without interception
        if fullname in ("kaira.__main__", "khaira.__main__"):
            return None

        candidates: list[str] = []
        if fullname.startswith("khaira."):
            sub = fullname[len("khaira.") :]
            candidates = [f"kaira.app.{sub}", f"kaira.{sub}"]
        elif fullname.startswith("kaira.") and not fullname.startswith("kaira.app."):
            sub = fullname[len("kaira.") :]
            top_sub = sub.split(".")[0]
            if top_sub in _APP_SUBMODULES:
                candidates = [f"kaira.app.{sub}"]
            else:
                return None
        else:
            return None

        _in_progress.add(fullname)
        try:
            for cand in candidates:
                try:
                    mod = importlib.import_module(cand)
                    spec = ModuleSpec(
                        fullname,
                        _ForwardLoader(mod),  # type: ignore[arg-type]
                        origin=getattr(mod, "__file__", None),
                    )
                    if hasattr(mod, "__path__"):
                        spec.submodule_search_locations = list(mod.__path__)
                    return spec
                except (ImportError, AttributeError):
                    continue
        finally:
            _in_progress.discard(fullname)

        return None


if not any(
    getattr(f, "__name__", "") == "_KairaSubmoduleFinder" for f in sys.meta_path
):
    sys.meta_path.insert(0, _KairaSubmoduleFinder)  # type: ignore[arg-type]

__all__ = [
    "APIRouter",
    "AsyncSession",
    "Base",
    "Database",
    "Depends",
    "Document",
    "HTTPException",
    "KairaApp",
    "KairaConfig",
    "KairaProvider",
    "KhairaApp",
    "KhairaConfig",
    "KhairaProvider",
    "Limiter",
    "Model",
    "Query",
    "RateLimiter",
    "Request",
    "Router",
    "Schema",
    "Session",
    "__author__",
    "__description__",
    "__homepage__",
    "__version__",
    "get_config",
    "get_remote_address",
    "limiter",
    "status",
]
