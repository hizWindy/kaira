"""Khaira — Automated FastAPI Scaffolding CLI and Framework Runtime."""

from __future__ import annotations

__version__ = "0.2.3"
__author__ = "Kaira"
__description__ = "Automated FastAPI scaffolding CLI and framework runtime."
__homepage__ = "https://github.com/hizWindy/kaira"

from kaira.app.kaira_app import KairaApp
from kaira.app.providers.base import KairaProvider
from kaira.config import KairaConfig, get_config
from kaira.app.models import Model, Document

KhairaApp = KairaApp
KhairaProvider = KairaProvider
KhairaConfig = KairaConfig

__all__ = [
    "__version__",
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
