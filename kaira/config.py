"""Global configuration and settings for Kaira."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

CONFIG_FILE = ".devflow.json"

SUPPORTED_FIELD_TYPES = {
    "str",
    "int",
    "float",
    "bool",
    "datetime",
    "Optional[str]",
    "Optional[int]",
    "Optional[float]",
    "Optional[bool]",
    "Optional[datetime]",
}

SQLALCHEMY_TYPE_MAP = {
    "str": "String",
    "int": "Integer",
    "float": "Float",
    "bool": "Boolean",
    "datetime": "DateTime",
    "Optional[str]": "String",
    "Optional[int]": "Integer",
    "Optional[float]": "Float",
    "Optional[bool]": "Boolean",
    "Optional[datetime]": "DateTime",
}

PYTHON_TYPE_MAP = {
    "str": "str",
    "int": "int",
    "float": "float",
    "bool": "bool",
    "datetime": "datetime",
    "Optional[str]": "Optional[str]",
    "Optional[int]": "Optional[int]",
    "Optional[float]": "Optional[float]",
    "Optional[bool]": "Optional[bool]",
    "Optional[datetime]": "Optional[datetime]",
}

LAYERS = ["model", "repository", "schema", "service", "router"]

TIER_LAYERS = {
    "simple": ["model", "schema", "router"],
    "full": ["model", "repository", "schema", "service", "router"],
}

LAYER_DIRS = {
    "model": "models",
    "repository": "repositories",
    "schema": "schemas",
    "service": "services",
    "router": "routers",
}

LAYER_SUFFIX = {
    "model": "",
    "repository": "_repository",
    "schema": "_schema",
    "service": "_service",
    "router": "_router",
}


@dataclass
class DevFlowConfig:
    """Project-level Kaira configuration."""

    output_dir: str = "."
    models_dir: str = "models"
    repositories_dir: str = "repositories"
    schemas_dir: str = "schemas"
    services_dir: str = "services"
    routers_dir: str = "routers"
    default_tier: str = "full"
    ai_provider: str = "openai"
    ai_model: str = "gpt-4o"
    ai_api_key_env: str = "OPENAI_API_KEY"
    generated_models: list[dict[str, Any]] = field(default_factory=list)
    # Phase 3 fields
    db_type: str = "sqlite"          # postgresql | mysql | mongodb | sqlite
    api_version: str = "v1"           # v1 | v2 | …
    auth_type: str = "none"           # jwt | oauth2 | api-key | none

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DevFlowConfig":
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def get_layer_dir(self, layer: str) -> str:
        mapping = {
            "model": self.models_dir,
            "repository": self.repositories_dir,
            "schema": self.schemas_dir,
            "service": self.services_dir,
            "router": self.routers_dir,
        }
        return mapping.get(layer, layer + "s")


def find_config_path() -> Path:
    """Search for .devflow.json starting from cwd, walking up."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        candidate = directory / CONFIG_FILE
        if candidate.exists():
            return candidate
    return Path.cwd() / CONFIG_FILE


def get_config() -> DevFlowConfig:
    """Load config from .devflow.json or return defaults."""
    config_path = find_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DevFlowConfig.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            return DevFlowConfig()
    return DevFlowConfig()


def save_config(config: DevFlowConfig) -> None:
    """Save config to .devflow.json in cwd."""
    config_path = Path.cwd() / CONFIG_FILE
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def get_output_root(config: Optional[DevFlowConfig] = None) -> Path:
    """Return the root output directory."""
    if config is None:
        config = get_config()
    return Path.cwd() / config.output_dir


def register_model(config: DevFlowConfig, model_name: str, fields: list[dict], relations: list[dict]) -> None:
    """Add or update a model entry in config's generated_models list."""
    for entry in config.generated_models:
        if entry.get("name") == model_name:
            entry["fields"] = fields
            entry["relations"] = relations
            return
    config.generated_models.append({"name": model_name, "fields": fields, "relations": relations})


def get_venv_python(cwd: Optional[Path] = None) -> str:
    """Find the virtual environment python in the current workspace or parent directories."""
    import sys
    import os
    if cwd is None:
        cwd = Path.cwd()
    # Walk up to find a directory containing .venv
    current = cwd
    for directory in [current, *current.parents]:
        venv_dir = directory / ".venv"
        if venv_dir.is_dir():
            if os.name == "nt":
                venv_python = venv_dir / "Scripts" / "python.exe"
            else:
                venv_python = venv_dir / "bin" / "python"
            if venv_python.exists():
                return str(venv_python)
            
        # Also check for env/ or venv/ just in case
        for name in ["venv", "env"]:
            v_dir = directory / name
            if v_dir.is_dir():
                if os.name == "nt":
                    v_python = v_dir / "Scripts" / "python.exe"
                else:
                    v_python = v_dir / "bin" / "python"
                if v_python.exists():
                    return str(v_python)

    return sys.executable
