"""Khaira — Automated FastAPI Scaffolding CLI and Framework Runtime."""

from __future__ import annotations

import importlib
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any, List, Optional, Set

import kaira

# Re-export everything from kaira
from kaira import (
    APIRouter,
    Depends,
    Document,
    HTTPException,
    KairaApp,
    KairaConfig,
    KairaProvider,
    KhairaApp,
    KhairaConfig,
    KhairaProvider,
    Model,
    Router,
    Schema,
    __author__,
    __description__,
    __homepage__,
    __version__,
    get_config,
    status,
)


class _ForwardLoader:
    def __init__(self, mod: ModuleType) -> None:
        self.mod = mod

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        return self.mod

    def exec_module(self, module: ModuleType) -> None:
        pass


_in_progress: Set[str] = set()


class _KhairaModuleFinder:
    """Dynamically route any khaira.<submodule> import to kaira.app.<submodule> or kaira.<submodule>."""

    @classmethod
    def find_spec(
        cls,
        fullname: str,
        path: Optional[List[str]] = None,
        target: Optional[ModuleType] = None,
    ) -> Any:
        if fullname in _in_progress:
            return None

        if not fullname.startswith("khaira."):
            return None

        sub = fullname[len("khaira.") :]
        candidates = [f"kaira.app.{sub}", f"kaira.{sub}"]

        _in_progress.add(fullname)
        try:
            for cand in candidates:
                try:
                    mod = importlib.import_module(cand)
                    spec = ModuleSpec(
                        fullname,
                        _ForwardLoader(mod),
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
    getattr(f, "__name__", "") == "_KhairaModuleFinder" for f in sys.meta_path
):
    sys.meta_path.insert(0, _KhairaModuleFinder)

__all__ = [
    "__version__",
    "__author__",
    "__description__",
    "__homepage__",
    "kaira",
    "KairaApp",
    "KhairaApp",
    "KairaProvider",
    "KhairaProvider",
    "KairaConfig",
    "KhairaConfig",
    "get_config",
    "Model",
    "Document",
    "Schema",
    "Router",
    "APIRouter",
    "Depends",
    "HTTPException",
    "status",
]
