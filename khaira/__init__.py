"""Khaira — Automated FastAPI Scaffolding CLI and Framework Runtime."""

from __future__ import annotations

import importlib
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any

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


class _KhairaModuleFinder:
    """Dynamically route any khaira.<submodule> import to kaira.app.<submodule> or kaira.<submodule>."""

    @classmethod
    def find_spec(
        cls,
        fullname: str,
        path: list[str] | None = None,
        target: ModuleType | None = None,
    ) -> Any:
        if fullname in _in_progress:
            return None

        if not fullname.startswith("khaira."):
            return None

        # Let physical files like khaira/__main__.py load via default machinery
        if fullname == "khaira.__main__":
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
    "APIRouter",
    "Depends",
    "Document",
    "HTTPException",
    "KairaApp",
    "KairaConfig",
    "KairaProvider",
    "KhairaApp",
    "KhairaConfig",
    "KhairaProvider",
    "Model",
    "Router",
    "Schema",
    "__author__",
    "__description__",
    "__homepage__",
    "__version__",
    "get_config",
    "kaira",
    "status",
]
