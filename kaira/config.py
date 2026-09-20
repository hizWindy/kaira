"""Global configuration and settings for Kaira."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

CONFIG_FILE = ".kaira.json"

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

# Fields auto-managed by the database / ORM — never exposed in Create schemas
# and excluded from user-field introspection in sync / seed.
SERVER_MANAGED_FIELDS = {"id", "uuid", "created_at", "updated_at"}

# Embedded (nested) document fields are stored as a JSON column on SQL engines
# and as a real sub-document on document stores. One declaration, both worlds.
EMBEDDED_SQLALCHEMY_TYPE = "JSON"

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
class KairaConfig:
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
    # Embedded (nested) document types usable as a field type on any model.
    # Each entry: {"name": "EmergencyContact", "fields": [{"name":…, "type":…}]}
    embedded_models: list[dict[str, Any]] = field(default_factory=list)
    # Phase 3 fields
    db_type: str = "sqlite"  # postgresql | mysql | mongodb | sqlite
    api_version: str = "v1"  # v1 | v2 | …
    auth_type: str = "none"  # jwt | oauth2 | api-key | none
    # Phase 6 — auto DB provisioning (Feature 1) + offline/online mode (Feature 3)
    db_name: str = ""  # sanitized database identifier
    db_provisioned: bool = False  # True once the DB has been created/confirmed
    db_mode: str = "online"  # online | offline | auto (Layer-1 default: online)
    # Feature flags read by the Docker services registry.  Commands that enable
    # a subsystem record it here so `kaira docker sync` can render the matching
    # compose service without re-deriving it from the filesystem every time.
    cache_enabled: bool = False  # Redis cache initialised
    task_enabled: bool = False  # Celery background tasks initialised
    search_provider: str = ""  # elasticsearch | meilisearch | ""
    monitor_provider: str = ""  # sentry | datadog | newrelic | ""
    # Monitoring surface (`kaira monitor init`).  Recorded per feature rather
    # than as one boolean so `monitor status` and Docker rendering can tell a
    # metrics-only project apart from one that also runs the mini dashboard.
    monitor_metrics: bool = False  # core/metrics.py + GET /metrics scaffolded
    monitor_probes: bool = False  # /healthz + /readyz scaffolded (/health untouched)
    monitor_dashboard: bool = False  # /_kaira/monitor mini dashboard scaffolded
    monitor_dashboard_auth: str = ""  # reuse | token | "" (dashboard disabled)
    monitor_json_logs: bool = False  # logger understands KAIRA_LOG_FORMAT=json
    docker_enabled: bool = False  # Dockerfile has been scaffolded
    docker_compose: bool = False  # compose files are part of the surface
    docker_python: str = ""  # Python version pinned in the Dockerfile
    # Framework Runtime fields (Phase 8)
    tier: str = "standard"  # simple | standard | enterprise
    kaira_version: str = "0.2.0"
    enforce_layers: bool = True  # Enforce 5-layer pipeline separation
    auto_register: bool = True  # Auto-register routers and models
    providers: list[str] = field(default_factory=lambda: ["cache", "auth"])
    orm: str = "sqlalchemy"  # sqlalchemy | sqlmodel | beanie | peewee | tortoise

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KairaConfig":
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
    """Search for .khaira.json or .kaira.json starting from cwd, walking up."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        for candidate_name in (".khaira.json", CONFIG_FILE):
            candidate = directory / candidate_name
            if candidate.exists():
                return candidate
    return Path.cwd() / CONFIG_FILE


def get_config() -> KairaConfig:
    """Load config from .kaira.json or return defaults."""
    config_path = find_config_path()
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return KairaConfig.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            return KairaConfig()
    return KairaConfig()


def save_config(config: KairaConfig) -> None:
    """Save config to .kaira.json in cwd."""
    config_path = Path.cwd() / CONFIG_FILE
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)


def set_config_values(**values: Any) -> None:
    """Patch individual keys in the project's .kaira.json, leaving the rest alone.

    Used by feature commands to record state (``cache_enabled``,
    ``search_provider``, …) without round-tripping the whole config through
    :class:`KairaConfig`, which would drop any key a newer Kaira wrote.

    Silently does nothing outside a Kaira project, so calling it is always safe.

    Args:
        **values: Config keys to set.
    """
    config_path = find_config_path()
    if not config_path.exists():
        return
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
        data.update(values)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except (OSError, json.JSONDecodeError):
        pass  # Never crash a command because a flag could not be recorded


def get_output_root(config: Optional[KairaConfig] = None) -> Path:
    """Return the root output directory."""
    if config is None:
        config = get_config()
    return Path.cwd() / config.output_dir


def register_model(
    config: KairaConfig, model_name: str, fields: list[dict], relations: list[dict]
) -> None:
    """Add or update a model entry in config's generated_models list."""
    for entry in config.generated_models:
        if entry.get("name") == model_name:
            entry["fields"] = fields
            entry["relations"] = relations
            return
    config.generated_models.append(
        {"name": model_name, "fields": fields, "relations": relations}
    )


def register_embedded_model(
    config: KairaConfig, model_name: str, fields: list[dict]
) -> None:
    """Add or update an embedded model entry in config's embedded_models list."""
    for entry in config.embedded_models:
        if entry.get("name") == model_name:
            entry["fields"] = fields
            return
    config.embedded_models.append({"name": model_name, "fields": fields})


def embedded_model_names(config: Optional[KairaConfig] = None) -> set[str]:
    """Return the set of registered embedded model names.

    Used by the field parser to decide whether a non-scalar type such as
    ``EmergencyContact`` is a known embedded document or a typo. Returns an
    empty set outside a Kaira project so parsing degrades to scalars only.
    """
    if config is None:
        try:
            config = get_config()
        except Exception:
            return set()
    return {
        entry["name"]
        for entry in getattr(config, "embedded_models", [])
        if entry.get("name")
    }


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
