"""Khaira — Automated FastAPI Scaffolding CLI and Framework Runtime."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from types import ModuleType
from typing import Any, List, Optional

import kaira

# Re-export everything from kaira
from kaira import (
    Document,
    KairaApp,
    KairaConfig,
    KairaProvider,
    Model,
    __author__,
    __description__,
    __homepage__,
    __version__,
    get_config,
)

# Khaira-named aliases
KhairaApp = KairaApp
KhairaProvider = KairaProvider
KhairaConfig = KairaConfig


class _KhairaModuleFinder:
    """Dynamically route any khaira.<submodule> import to kaira.<submodule>."""

    @classmethod
    def find_spec(
        cls,
        fullname: str,
        path: Optional[List[str]] = None,
        target: Optional[ModuleType] = None,
    ) -> Any:
        if fullname.startswith("khaira."):
            real_name = "kaira." + fullname[len("khaira.") :]
            try:
                real_mod = importlib.import_module(real_name)
                sys.modules[fullname] = real_mod
                return importlib.util.find_spec(real_name)
            except Exception:
                return None
        return None


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
]
