"""Rendering, state projection, and drift detection for generated documentation.

Projections of internal state into clean Markdown files:
- docs/models.md        Model reference (fields, constraints, relations)
- docs/endpoints.md     Endpoint reference (routes, methods, auth, cache, rate limits)
- docs/erd.md           Entity Relationship Diagram (Mermaid erDiagram)
- docs/configuration.md Configuration reference (env keys, placeholders, features)
- docs/README.md        Navigation index
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.text import Text

from kaira import __version__
from kaira.config import (
    SERVER_MANAGED_FIELDS,
    KairaConfig,
    embedded_model_names,
    get_config,
    save_config,
)
from kaira.console import console
from kaira.core.detector import compute_diff
from kaira.core.parser import camel_to_snake
from kaira.core.route_discovery import discover_routes
from kaira.core.theme import Theme, is_interactive

DOC_MODELS = "models.md"
DOC_ENDPOINTS = "endpoints.md"
DOC_ERD = "erd.md"
DOC_CONFIG = "configuration.md"
DOC_README = "README.md"

ALL_DOC_FILES = (DOC_README, DOC_MODELS, DOC_ENDPOINTS, DOC_ERD, DOC_CONFIG)

DOC_KEY_TO_FILE = {
    "models": DOC_MODELS,
    "endpoints": DOC_ENDPOINTS,
    "erd": DOC_ERD,
    "config": DOC_CONFIG,
    "configuration": DOC_CONFIG,
    "readme": DOC_README,
}

DOC_METADATA = {
    "README.md": {
        "title": "Project Root Overview",
        "description": "Project root overview, architecture, models & quickstart guide",
        "location": "Project Root",
    },
    "docs/README.md": {
        "title": "Documentation Index",
        "description": "Documentation suite navigation index & API specifications",
        "location": "Documentation Folder",
    },
    "docs/models.md": {
        "title": "Model Reference",
        "description": "Database models, field types, validation constraints & relations",
        "location": "Documentation Folder",
    },
    "docs/endpoints.md": {
        "title": "Endpoint Reference",
        "description": "Discovered API routes, auth requirements, cache & rate limits",
        "location": "Documentation Folder",
    },
    "docs/erd.md": {
        "title": "Entity Relationship Diagram",
        "description": "Mermaid visual ER diagram with cardinality mappings",
        "location": "Documentation Folder",
    },
    "docs/configuration.md": {
        "title": "Configuration Reference",
        "description": "Environment variable keys, requirements & feature flags",
        "location": "Documentation Folder",
    },
}

# ---------------------------------------------------------------------------
# Env Registry Metadata (Key -> {feature, required, placeholder, description})
# NEVER reads from live .env files. Only documents known registry definitions.
# ---------------------------------------------------------------------------

ENV_REGISTRY_METADATA: dict[str, dict[str, str | bool]] = {
    "APP_ENV": {
        "feature": "core",
        "required": True,
        "placeholder": "development | staging | production",
        "description": "Application environment runtime mode",
    },
    "APP_NAME": {
        "feature": "core",
        "required": True,
        "placeholder": "<project_name>",
        "description": "Human-readable application name",
    },
    "DEBUG": {
        "feature": "core",
        "required": False,
        "placeholder": "true | false",
        "description": "Enable debug mode (auto-reload & detailed errors)",
    },
    "DATABASE_URL": {
        "feature": "core",
        "required": True,
        "placeholder": "postgresql://<user>:<password>@<host>:<port>/<dbname>",
        "description": "Primary database connection URL",
    },
    "ALLOWED_ORIGINS": {
        "feature": "core",
        "required": True,
        "placeholder": '["http://localhost:3000","http://localhost:8000"]',
        "description": "Allowed CORS origins as JSON list",
    },
    "RATE_LIMIT_GET": {
        "feature": "core",
        "required": False,
        "placeholder": "60/minute",
        "description": "Default rate limit for read operations",
    },
    "RATE_LIMIT_WRITE": {
        "feature": "core",
        "required": False,
        "placeholder": "30/minute",
        "description": "Default rate limit for write/mutation operations",
    },
    "JWT_SECRET_KEY": {
        "feature": "auth",
        "required": True,
        "placeholder": "<minimum-32-character-secret-key>",
        "description": "Secret key for signing JSON Web Tokens",
    },
    "JWT_ALGORITHM": {
        "feature": "auth",
        "required": False,
        "placeholder": "HS256",
        "description": "Cryptographic algorithm for JWT encoding",
    },
    "ACCESS_TOKEN_EXPIRE_MINUTES": {
        "feature": "auth",
        "required": False,
        "placeholder": "30",
        "description": "Access token lifetime in minutes",
    },
    "REDIS_URL": {
        "feature": "cache",
        "required": True,
        "placeholder": "redis://<host>:6379/0",
        "description": "Redis connection URL for cache & broker",
    },
    "CACHE_TTL": {
        "feature": "cache",
        "required": False,
        "placeholder": "300",
        "description": "Default cache TTL in seconds",
    },
    "CELERY_BROKER_URL": {
        "feature": "task",
        "required": True,
        "placeholder": "redis://<host>:6379/0",
        "description": "Message broker URL for Celery worker tasks",
    },
    "CELERY_RESULT_BACKEND": {
        "feature": "task",
        "required": False,
        "placeholder": "redis://<host>:6379/0",
        "description": "Result store backend URL for Celery",
    },
    "FLOWER_PORT": {
        "feature": "task",
        "required": False,
        "placeholder": "5555",
        "description": "Web port for Celery Flower monitoring dashboard",
    },
    "SUPABASE_DB_URL": {
        "feature": "cloud",
        "required": True,
        "placeholder": "postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require",
        "description": "Pooled connection URL for Supabase PostgreSQL",
    },
    "SUPABASE_DB_URL_DIRECT": {
        "feature": "cloud",
        "required": True,
        "placeholder": "postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require",
        "description": "Direct connection URL for migrations on Supabase",
    },
    "ATLAS_URI": {
        "feature": "cloud",
        "required": True,
        "placeholder": "mongodb+srv://<user>:<password>@<cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority",
        "description": "MongoDB Atlas connection URI with TLS",
    },
    "FIREBASE_CREDENTIALS_PATH": {
        "feature": "cloud",
        "required": True,
        "placeholder": "/path/to/firebase-credentials.json",
        "description": "Path to Firebase service account credentials file",
    },
    "FIREBASE_PROJECT_ID": {
        "feature": "cloud",
        "required": True,
        "placeholder": "<firebase-project-id>",
        "description": "Google Cloud / Firebase Project ID",
    },
    "FALLBACK_ENABLED": {
        "feature": "fallback",
        "required": False,
        "placeholder": "true | false",
        "description": "Enable automatic fallback to local database if cloud is down",
    },
    "FALLBACK_PROBE_INTERVAL": {
        "feature": "fallback",
        "required": False,
        "placeholder": "30",
        "description": "Interval in seconds between cloud health probes",
    },
    "SENDGRID_API_KEY": {
        "feature": "email",
        "required": True,
        "placeholder": "SG.<sendgrid-api-key>",
        "description": "SendGrid API key for transactional emails",
    },
    "MAILGUN_API_KEY": {
        "feature": "email",
        "required": True,
        "placeholder": "key-<mailgun-api-key>",
        "description": "Mailgun API key for transactional emails",
    },
    "STRIPE_API_KEY": {
        "feature": "payment",
        "required": True,
        "placeholder": "pk_test_<stripe-publishable-key>",
        "description": "Stripe publishable API key",
    },
    "STRIPE_SECRET_KEY": {
        "feature": "payment",
        "required": True,
        "placeholder": "sk_test_<stripe-secret-key>",
        "description": "Stripe secret API key",
    },
}


# ---------------------------------------------------------------------------
# Fingerprint & Comment Helpers
# ---------------------------------------------------------------------------


def _compute_fingerprint(data: str) -> str:
    """Return a short SHA-256 hash string for change detection."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def _build_footer(doc_key: str, state_str: str) -> str:
    """Build a deterministic footer comment with state fingerprint."""
    fp = _compute_fingerprint(state_str)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f'\n\n<!-- kaira:docs doc="{doc_key}" fingerprint="{fp}" generated_at="{now}" -->\n'


def _extract_fingerprint(file_content: str) -> Optional[str]:
    """Read fingerprint from the footer comment of a generated Markdown file."""
    match = re.search(r'<!--\s*kaira:docs\s+.*?fingerprint="([a-f0-9]+)"', file_content)
    return match.group(1) if match else None


def _extract_generated_at(file_content: str) -> Optional[str]:
    """Read generated_at from the footer comment of a generated Markdown file."""
    match = re.search(r'<!--\s*kaira:docs\s+.*?generated_at="([^"]+)"', file_content)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Model Fallback & Introspection
# ---------------------------------------------------------------------------


def _ensure_models_snapshot(config: KairaConfig, root: Path) -> list[dict]:
    """Return the models snapshot from config, deriving from files if missing."""
    if config.generated_models:
        return config.generated_models

    from kaira.commands.sync_cmd import _parse_model_fields

    models_dir = root / config.models_dir
    if not models_dir.is_dir():
        return []

    discovered: list[dict] = []
    embedded = embedded_model_names(config)

    for path in sorted(models_dir.glob("*.py")):
        if path.name.startswith("__") or path.name.endswith("_association.py"):
            continue
        fields = _parse_model_fields(path, embedded=embedded)
        if fields is not None:
            # Model name is derived from file stem, e.g. user -> User
            model_name = "".join(word.capitalize() for word in path.stem.split("_"))
            model_entry = {
                "name": model_name,
                "fields": [{"name": f.name, "type": f.raw_type} for f in fields],
                "relations": [],
            }
            discovered.append(model_entry)
            config.generated_models.append(model_entry)

    if discovered:
        save_config(config)

    return config.generated_models


def _field_constraints(name: str, raw_type: str) -> str:
    """Return explicit Pydantic & database constraints for a field."""
    constraints: list[str] = []
    if name in ("id", "uuid"):
        return "primary, external identifier"
    if name in ("created_at", "updated_at"):
        return "server-managed timestamp"

    if name == "email":
        return "max_length=255, pattern=email"
    if name == "phone":
        return "max_length=20, pattern=E.164"
    if name == "password":
        return "min_length=8, max_length=128"
    if name == "username":
        return "min_length=3, max_length=50, pattern=^[a-zA-Z0-9_]+$"

    if "str" in raw_type.lower():
        constraints.append("max_length=255")

    if not constraints:
        constraints.append("—")

    return ", ".join(constraints)


# ---------------------------------------------------------------------------
# 1. Model Reference: docs/models.md
# ---------------------------------------------------------------------------


def _render_single_model_section(model: dict, db_type: str = "sqlite") -> str:
    """Render a single model's Markdown documentation section."""
    name = model.get("name", "Unnamed")
    fields = model.get("fields", [])
    relations = model.get("relations", [])

    lines: list[str] = [
        f"## {name}",
        "",
        "### Fields",
        "",
        "| Field | Type | Constraints | Nullable | Notes |",
        "|---|---|---|---|---|",
    ]

    # Primary key
    pk_type = (
        "str" if db_type in ("mongodb", "atlas", "firebase", "firestore") else "UUID"
    )
    lines.append(f"| `id` | `{pk_type}` | primary, external identifier | No | — |")

    for f in fields:
        fname = f.get("name", "")
        ftype = f.get("type", "str")
        if fname in SERVER_MANAGED_FIELDS:
            continue

        nullable = "Yes" if "optional[" in ftype.lower() else "No"
        clean_type = ftype.replace("Optional[", "").replace("]", "")
        constraints = _field_constraints(fname, clean_type)
        lines.append(f"| `{fname}` | `{clean_type}` | {constraints} | {nullable} | — |")

    # Timestamps
    lines.append("| `created_at` | `datetime` | server-managed timestamp | No | — |")
    lines.append("| `updated_at` | `datetime` | server-managed timestamp | No | — |")

    if relations:
        lines.extend(["", "### Relationships", ""])
        for rel in relations:
            rtype = rel.get("type", "one-to-many")
            target = rel.get("target", "")
            target_anchor = target.lower()
            if rtype == "one-to-many":
                lines.append(
                    f"- → has many [{target}](#{target_anchor}) ([ERD](erd.md#{target_anchor}))"
                )
            elif rtype == "many-to-one":
                lines.append(
                    f"- → belongs to [{target}](#{target_anchor}) ([ERD](erd.md#{target_anchor}))"
                )
            elif rtype == "many-to-many":
                lines.append(
                    f"- ↔ relates to many [{target}](#{target_anchor}) ([ERD](erd.md#{target_anchor}))"
                )
            elif rtype == "one-to-one":
                lines.append(
                    f"- ↔ has one [{target}](#{target_anchor}) ([ERD](erd.md#{target_anchor}))"
                )

    return "\n".join(lines)


def render_models_doc(
    config: KairaConfig,
    root: Path,
    target_model: Optional[str] = None,
    existing_content: Optional[str] = None,
) -> str:
    """Render `docs/models.md` for all models or surgically update one model."""
    models = _ensure_models_snapshot(config, root)
    db_type = getattr(config, "db_type", "sqlite")

    if target_model:
        # Surgical single-model update preserving the rest of docs/models.md
        target_entry = next(
            (m for m in models if m.get("name", "").lower() == target_model.lower()),
            None,
        )
        if not target_entry:
            # Fallback entry
            target_entry = {"name": target_model, "fields": [], "relations": []}

        new_section = _render_single_model_section(target_entry, db_type=db_type)

        if not existing_content or not existing_content.strip():
            # Generate new file containing the header and this model
            content = f"# Model Reference\n\nData models and field specifications for the project.\n\n{new_section}"
        else:
            # Replace existing section or append
            pattern = rf"(?ms)^##\s+{re.escape(target_entry['name'])}\b.*?(?=^##\s+|\Z)"
            if re.search(pattern, existing_content):
                content = re.sub(
                    pattern, new_section.rstrip() + "\n\n", existing_content
                )
            else:
                # Remove old footer if present
                clean_existing = re.sub(
                    r"\n\n<!--\s*kaira:docs.*?\Z", "", existing_content.rstrip()
                )
                content = f"{clean_existing}\n\n---\n\n{new_section}"

        state_str = json.dumps(models, sort_keys=True)
        # Strip existing footer before appending current footer
        clean_content = re.sub(r"\n\n<!--\s*kaira:docs.*?\Z", "", content.rstrip())
        return clean_content + _build_footer("models", state_str)

    # Full document generation
    sections: list[str] = [
        "# Model Reference",
        "",
        "Data models, schema constraints, and entity relationships.",
        "",
    ]

    if not models:
        sections.append(
            "*No models registered. Scaffold a model with `kaira generate model <Name>`.*"
        )
    else:
        for model in models:
            sections.append(_render_single_model_section(model, db_type=db_type))
            sections.append("")

    full_text = "\n".join(sections).rstrip()
    state_str = json.dumps(models, sort_keys=True)
    return full_text + _build_footer("models", state_str)


# ---------------------------------------------------------------------------
# 2. Endpoint Reference: docs/endpoints.md
# ---------------------------------------------------------------------------


def render_endpoints_doc(config: KairaConfig, root: Path) -> str:
    """Render `docs/endpoints.md` grouped by resource."""
    model_names: set[str] = {
        str(m.get("name")) for m in config.generated_models if m.get("name")
    }
    api_prefix = f"/api/{getattr(config, 'api_version', 'v1')}"

    groups, _ = discover_routes(
        root,
        model_names,
        prefer_live=True,
        api_prefix=api_prefix,
    )

    cache_enabled = (root / "core" / "cache.py").exists() or getattr(
        config, "cache_enabled", False
    )

    lines: list[str] = [
        "# Endpoint Reference",
        "",
        "Discovered API routes grouped by resource with security, cache, and rate-limit policies.",
        "",
    ]

    if not groups:
        lines.append("*No endpoints discovered in project.*")
    else:
        for group in groups:
            lines.append(f"## {group.name}")
            lines.append("")
            lines.append("| Route | Method | Auth | Cached | Rate limit |")
            lines.append("|---|---|---|---|---|")

            for ep in group.endpoints:
                auth_disp = "🔒 Required" if ep.auth_required else "—"
                is_get = ep.method.upper() == "GET"
                cached_disp = (
                    "300s"
                    if (cache_enabled and is_get and group.kind == "model")
                    else "—"
                )
                rate_limit_disp = "60/min" if is_get else "30/min"
                lines.append(
                    f"| `{ep.path}` | `{ep.method}` | {auth_disp} | {cached_disp} | {rate_limit_disp} |"
                )

            lines.append("")

    lines.extend(
        [
            "---",
            "",
            "*For machine-readable formats, use `kaira api export` (OpenAPI spec) and `kaira api postman` (Postman collection).*",
        ]
    )

    full_text = "\n".join(lines).rstrip()

    # Fingerprint state based on endpoints signatures and auth
    all_sig = ";".join(
        f"{g.name}:{e.method}:{e.path}:{e.auth_required}"
        for g in groups
        for e in g.endpoints
    )
    return full_text + _build_footer("endpoints", all_sig)


# ---------------------------------------------------------------------------
# 3. ERD: docs/erd.md
# ---------------------------------------------------------------------------


def render_erd_doc(config: KairaConfig, root: Path) -> str:
    """Render `docs/erd.md` Mermaid Entity Relationship Diagram."""
    models = _ensure_models_snapshot(config, root)
    db_type = getattr(config, "db_type", "sqlite").lower()
    is_doc_db = db_type in ("mongodb", "atlas", "firebase", "firestore")

    lines: list[str] = [
        "# Entity Relationship Diagram",
        "",
    ]

    if is_doc_db:
        lines.extend(
            [
                "> **Note:** Document relationships (logical) — document stores have logical relationships rather than enforced foreign keys.",
                "",
            ]
        )

    lines.extend(
        [
            "```mermaid",
            "erDiagram",
        ]
    )

    if not models:
        lines.append("    EMPTY_PROJECT {")
        lines.append("        string message")
        lines.append("    }")
    else:
        # Render entities
        for model in models:
            name = model.get("name", "Unnamed")
            fields = model.get("fields", [])
            lines.append(f"    {name} {{")
            pk_type = "string" if is_doc_db else "UUID"
            lines.append(f"        {pk_type} id PK")

            count = 0
            for f in fields:
                fname = f.get("name", "")
                ftype = f.get("type", "str").replace("Optional[", "").replace("]", "")
                if fname in SERVER_MANAGED_FIELDS:
                    continue
                mermaid_type = "string"
                if "int" in ftype.lower():
                    mermaid_type = "int"
                elif "float" in ftype.lower():
                    mermaid_type = "float"
                elif "bool" in ftype.lower():
                    mermaid_type = "boolean"
                elif "datetime" in ftype.lower():
                    mermaid_type = "datetime"

                if count < 8:
                    lines.append(f"        {mermaid_type} {fname}")
                    count += 1
                elif count == 8:
                    remaining = len(fields) - 8
                    if remaining > 0:
                        lines.append(
                            f'        string more_fields "... {remaining} more fields"'
                        )
                    count += 1

            lines.append("        datetime created_at")
            lines.append("        datetime updated_at")
            lines.append("    }")

        # Render relationships
        lines.append("")
        seen_rels: set[str] = set()
        for model in models:
            src = model.get("name", "")
            for rel in model.get("relations", []):
                rtype = rel.get("type", "one-to-many")
                tgt = rel.get("target", "")
                if not tgt:
                    continue

                rel_key = f"{src}-{rtype}-{tgt}"
                if rel_key in seen_rels:
                    continue
                seen_rels.add(rel_key)

                if is_doc_db:
                    # Document logical connection
                    lines.append(f'    {src} .. {tgt} : "references"')
                else:
                    if rtype == "one-to-many":
                        lines.append(f'    {src} ||--o{{ {tgt} : "has many"')
                    elif rtype == "many-to-one":
                        lines.append(f'    {src} }}o--|| {tgt} : "belongs to"')
                    elif rtype == "many-to-many":
                        lines.append(f'    {src} }}o--o{{ {tgt} : "relates to"')
                    elif rtype == "one-to-one":
                        lines.append(f'    {src} ||--|| {tgt} : "has one"')

    lines.extend(
        [
            "```",
            "",
        ]
    )

    full_text = "\n".join(lines).rstrip()
    state_str = json.dumps(models, sort_keys=True) + f":{db_type}"
    return full_text + _build_footer("erd", state_str)


# ---------------------------------------------------------------------------
# 4. Configuration Reference: docs/configuration.md
# ---------------------------------------------------------------------------


def render_configuration_doc(config: KairaConfig, root: Path) -> str:
    """Render `docs/configuration.md` with env registry keys and feature flags.

    SECURITY: NEVER reads live `.env` files or environment variables.
    """
    from kaira.commands.env_cmd import _feature_enabled

    lines: list[str] = [
        "# Configuration Reference",
        "",
        "Project environment variable keys, ownership, requirements, and placeholder formats.",
        "",
        "## Feature Flags",
        "",
        "| Feature | State | Notes |",
        "|---|---|---|",
    ]

    # Feature flags from state
    db_type = getattr(config, "db_type", "sqlite")
    lines.append(f"| `Database` | `{db_type}` | Configured database engine |")

    auth_type = getattr(config, "auth_type", "none")
    lines.append(f"| `Authentication` | `{auth_type}` | Identity & token strategy |")

    cache_on = _feature_enabled("cache", config, root)
    lines.append(
        f"| `Redis Cache` | `{'Enabled' if cache_on else 'Disabled'}` | In-memory key-value caching |"
    )

    task_on = _feature_enabled("task", config, root)
    lines.append(
        f"| `Background Tasks` | `{'Enabled' if task_on else 'Disabled'}` | Celery task worker queue |"
    )

    docker_on = (root / "Dockerfile").is_file() or getattr(
        config, "docker_enabled", False
    )
    lines.append(
        f"| `Docker` | `{'Enabled' if docker_on else 'Disabled'}` | Container & compose surface |"
    )

    cloud_on = _feature_enabled("cloud", config, root)
    lines.append(
        f"| `Cloud DB` | `{'Enabled' if cloud_on else 'Disabled'}` | Managed cloud provider |"
    )

    fallback_on = _feature_enabled("fallback", config, root)
    lines.append(
        f"| `Cloud Fallback` | `{'Enabled' if fallback_on else 'Disabled'}` | Local database fallback |"
    )

    lines.extend(
        [
            "",
            "## Environment Variables",
            "",
            "| Key | Feature | Required | Placeholder Format | Status |",
            "|---|---|---|---|---|",
        ]
    )

    for key, meta in sorted(ENV_REGISTRY_METADATA.items()):
        feat = str(meta["feature"])
        req = "Yes" if meta["required"] else "No"
        ph = str(meta["placeholder"])
        is_enabled = _feature_enabled(feat, config, root)
        status = "Active" if is_enabled else "Unused"
        lines.append(f"| `{key}` | `{feat}` | {req} | `{ph}` | {status} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "> **Security Note:** Secrets and credentials must never be committed to source control. "
            "Populate `.env.development` or `.env.production` locally using the placeholders above.",
        ]
    )

    full_text = "\n".join(lines).rstrip()

    # Fingerprint state based on active features
    feat_states = {
        k: _feature_enabled(str(v["feature"]), config, root)
        for k, v in ENV_REGISTRY_METADATA.items()
    }
    state_str = json.dumps(feat_states, sort_keys=True)
    return full_text + _build_footer("configuration", state_str)


# ---------------------------------------------------------------------------
# 5. README Index: docs/README.md
# ---------------------------------------------------------------------------


def render_readme_doc(config: KairaConfig, root: Path) -> str:
    """Render `docs/README.md` navigation index with purpose and architectural overview."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    project_name = getattr(config, "project_name", None) or root.name or "Backend API"
    db_type = getattr(config, "db_type", "sqlite")
    auth_type = getattr(config, "auth_type", "none")
    api_version = getattr(config, "api_version", "v1")
    models = config.generated_models or []
    model_names = [str(m.get("name")) for m in models if m.get("name")]

    db_desc = (
        "SQLAlchemy ORM" if db_type != "mongodb" else "Document Store / MongoEngine"
    )
    if auth_type == "jwt":
        auth_desc = "OAuth2 JWT Bearer Tokens"
    elif auth_type == "api-key":
        auth_desc = "API Key header authentication"
    else:
        auth_desc = "Public / Unauthenticated"

    lines = [
        f"# {project_name} — Project Documentation",
        "",
        "Welcome to the architectural specification and API documentation for this backend service.",
        "",
        "## Purpose",
        "",
        f"This backend service provides a robust, scalable REST API built with FastAPI. It serves as the primary data and business logic foundation for **{project_name}**, handling secure request routing, data validation, database persistence, and domain workflows.",
        "",
        "Key objectives:",
        "- **Data Management**: Expose structured CRUD operations and specialized business logic endpoints.",
        "- **Validation & Integrity**: Enforce request/response contracts using Pydantic v2 schemas and database-level constraints.",
        "- **Modularity & Scalability**: Follow a strict 5-layer separation of concerns (Models, Repositories, Schemas, Services, Routers) for long-term maintainability.",
        "",
        "## Overview",
        "",
        "### System Architecture",
        "",
        "The project follows a 5-layer modular architecture to isolate responsibilities:",
        "1. **Routers (`routers/`)**: Declare HTTP endpoint routes, request/response models, and dependency injection.",
        "2. **Services (`services/`)**: Encapsulate domain rules, cross-repository coordination, and business logic.",
        "3. **Schemas (`schemas/`)**: Define Pydantic v2 validation models for request bodies, query parameters, and responses.",
        "4. **Repositories (`repositories/`)**: Manage data access queries and ORM operations.",
        "5. **Models (`models/`)**: Declare database entity definitions and relational schemas.",
        "",
        "### Technical Stack & Configuration",
        "",
        "- **Framework**: FastAPI (Python 3.10+)",
        f"- **API Version**: `/api/{api_version}`",
        f"- **Database**: `{db_type.upper()}` ({db_desc})",
        f"- **Authentication**: `{auth_type.upper()}` ({auth_desc})",
        f"- **Domain Models**: {', '.join(f'`{m}`' for m in model_names) if model_names else 'No models registered yet'}",
        "",
        "## Navigation",
        "",
        "- [Model Reference](models.md) — Schema definitions, field types, constraints, and relationships.",
        "- [Endpoint Reference](endpoints.md) — Discovered API routes grouped by resource, auth requirements, cache, and rate limits.",
        "- [Entity Relationship Diagram](erd.md) — Mermaid ERD diagram showing models and relationships.",
        "- [Configuration Reference](configuration.md) — Environment variable keys, ownership, requirements, and placeholder formats.",
        "",
        "## API Specifications",
        "",
        "For machine-readable API specifications:",
        "- `kaira api export --format json|yaml` — Export OpenAPI specification.",
        "- `kaira api postman` — Generate Postman collection.",
        "",
        "---",
        "",
        f"*Generated on {now} with Khaira v{__version__}.*",
    ]

    full_text = "\n".join(lines).rstrip()
    state_str = f"index:{__version__}:{project_name}:{db_type}:{auth_type}:{len(models)}:{','.join(sorted(model_names))}"
    return full_text + _build_footer("readme", state_str)


def render_root_readme_doc(config: KairaConfig, root: Path) -> str:
    """Render the project root `README.md` with complete overview, quickstart, architecture, and docs links."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    project_name = getattr(config, "project_name", None) or root.name or "Backend API"
    project_slug = getattr(config, "project_slug", None) or camel_to_snake(
        project_name
    ).replace("_", "-")
    db_type = getattr(config, "db_type", "sqlite")
    auth_type = getattr(config, "auth_type", "none")
    api_version = getattr(config, "api_version", "v1")
    models = config.generated_models or []
    model_names = [str(m.get("name")) for m in models if m.get("name")]

    db_desc = (
        "SQLAlchemy Async 2.0 + Alembic"
        if db_type != "mongodb"
        else "Beanie (MongoDB ODM)"
    )
    if auth_type == "jwt":
        auth_desc = "OAuth2 JWT Bearer Authentication"
    elif auth_type == "api-key":
        auth_desc = "API Key Header Authentication"
    else:
        auth_desc = "Public / None"

    lines = [
        f"# {project_name} ⚡",
        "",
        "**Modern, production-ready FastAPI backend service** scaffolded and managed with **Kaira**.",
        "",
        "---",
        "",
        "## Overview & Purpose",
        "",
        f"**{project_name}** is a scalable, modular RESTful API service providing high-performance request routing, business logic execution, and database persistence. It is engineered with strict type safety (Python 3.10+ and Pydantic v2), asynchronous database sessions, comprehensive security middleware, and a robust 5-layer separation of concerns.",
        "",
        "### Key Capabilities",
        "",
        "- **Layered Architecture**: Strict decoupling across Models, Repositories, Schemas, Services, and Routers.",
        f"- **API Versioning**: Active routes mounted under `/api/{api_version}`.",
        f"- **Database Engine**: `{db_type.upper()}` powered by {db_desc}.",
        f"- **Authentication**: `{auth_type.upper()}` ({auth_desc}).",
        "- **Security & Hardening**: Pre-configured CORS protection, SlowAPI rate limiting, and trusted security headers.",
        "- **Structured Logging**: Zero-clutter Loguru structured logger with production JSON support.",
        "- **Developer Tooling**: Fully integrated test suites, database migration scripts, Docker compose profiles, and automatic docs synchronization.",
        "",
        "---",
        "",
        "## Architecture & Directory Structure",
        "",
        "```text",
        "├── models/             # Database ORM/ODM entity definitions",
        "├── repositories/       # Data-access repository layers",
        "├── schemas/            # Pydantic v2 validation and serialization schemas",
        "├── services/           # Business logic and domain service layers",
        "├── routers/            # FastAPI endpoint routers and dependency injection",
        "├── auth/               # Authentication handlers, JWT tokens, and guards",
        "├── core/               # Database engine, connection sessions, and logging",
        "├── middleware/         # Rate limiting, CORS, and error-handling middleware",
        "├── tests/              # Pytest unit and integration test suites",
        "├── docs/               # Auto-generated project reference documentation",
        "├── main.py             # FastAPI application entrypoint",
        "├── requirements.txt    # Pinned dependency requirements",
        "├── pyproject.toml      # Project configuration and tool settings",
        "└── .kaira.json         # Kaira project state and model registry",
        "```",
        "",
        "---",
        "",
        "## Registered Domain Models",
        "",
    ]

    if model_names:
        lines.append("| Model | Fields | Relationships | Documentation |")
        lines.append("|---|---|---|---|")
        for m in models:
            m_name = m.get("name", "")
            f_count = len(m.get("fields", []))
            rels = m.get("relations", [])
            rel_str = (
                ", ".join(f"{r.get('type')}: {r.get('target')}" for r in rels)
                if rels
                else "—"
            )
            lines.append(
                f"| **`{m_name}`** | {f_count} fields | {rel_str} | [View Schema](docs/models.md#{m_name.lower()}) |"
            )
        lines.append("")
    else:
        lines.extend(
            [
                "*No models registered yet. Generate your first model:*",
                "```bash",
                'kaira generate model User --fields "username:str, email:str, is_active:bool"',
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Quick Start",
            "",
            "### 1. Setup Environment & Virtualenv",
            "",
            "```bash",
            "# Clone repository and navigate to project root",
            f"cd {project_slug}",
            "",
            "# Copy environment configuration",
            "cp .env.example .env",
            "",
            "# Create and activate virtual environment",
            "python -m venv .venv",
            "source .venv/bin/activate        # Windows: .venv\\Scripts\\activate",
            "",
            "# Install dependencies",
            "pip install -r requirements.txt",
            "```",
            "",
        ]
    )

    if db_type != "sqlite":
        lines.extend(
            [
                "### 2. Start Database",
                "",
                "```bash",
                "# Launch database container with Docker Compose",
                "docker compose up -d db",
                "```",
                "",
            ]
        )

    if db_type != "mongodb":
        lines.extend(
            [
                "### 3. Run Database Migrations",
                "",
                "```bash",
                "alembic upgrade head",
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "### 4. Start the Application",
            "",
            "```bash",
            "# Run with FastAPI dev server (hot reload enabled)",
            "fastapi dev main.py",
            "",
            "# Or run using Uvicorn directly",
            "uvicorn main:app --reload --port 8000",
            "```",
            "",
            "Once running, access:",
            "- **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)",
            "- **Alternative ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)",
            "- **Health Check Endpoint**: [http://localhost:8000/health](http://localhost:8000/health)",
            "",
            "---",
            "",
            "## Project Documentation",
            "",
            "Comprehensive architectural and API reference documents are maintained in the [`docs/`](docs/) directory:",
            "",
            "- 📘 **[docs/models.md](docs/models.md)** — Complete model reference, field types, validation constraints, and foreign key relations.",
            "- 🛣️ **[docs/endpoints.md](docs/endpoints.md)** — Discovered HTTP routes, auth guards, cache TTL, and rate limits.",
            "- 📊 **[docs/erd.md](docs/erd.md)** — Live Mermaid entity-relationship diagram with exact cardinalities.",
            "- ⚙️ **[docs/configuration.md](docs/configuration.md)** — Environment variables, configuration keys, and feature flags.",
            "- 📑 **[docs/README.md](docs/README.md)** — Navigation index for the documentation suite.",
            "",
            "---",
            "",
            "## Kaira CLI Management Commands",
            "",
            "Use Kaira to evolve and maintain the backend without manual boilerplate:",
            "",
            "```bash",
            "# Inspect documentation freshness",
            "kaira docs status",
            "",
            "# Regenerate all project documentation",
            "kaira docs generate",
            "",
            "# Add a new model pipeline (model, repo, schema, service, router)",
            'kaira generate model Product --fields "title:str, price:float, stock:int"',
            "",
            "# Add a relationship between models",
            'kaira add relation User --has-many Order --cascade "all, delete-orphan"',
            "",
            "# Synchronize model field changes across all layers",
            'kaira sync model User --fields "phone:str"',
            "",
            "# Export OpenAPI specification or Postman collection",
            "kaira api export --format json",
            "kaira api postman",
            "```",
            "",
            "---",
            "",
            f"*Project documentation generated on {now} with Khaira v{__version__}.*",
        ]
    )

    full_text = "\n".join(lines).rstrip()
    state_str = f"root_readme:{__version__}:{project_name}:{db_type}:{auth_type}:{len(models)}:{','.join(sorted(model_names))}"
    return full_text + _build_footer("root_readme", state_str)


# ---------------------------------------------------------------------------
# Full Surface Rendering & Plan Management
# ---------------------------------------------------------------------------


def render_all_docs(
    config: KairaConfig,
    root: Path,
    target_model: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> dict[str, str]:
    """Render mapping of relative doc path -> content for the documentation surface."""
    out_dir = output_dir or (root / "docs")

    if target_model:
        models_path = out_dir / DOC_MODELS
        existing = (
            models_path.read_text(encoding="utf-8") if models_path.is_file() else ""
        )
        return {
            DOC_MODELS: render_models_doc(
                config, root, target_model=target_model, existing_content=existing
            )
        }

    return {
        DOC_README: render_readme_doc(config, root),
        DOC_MODELS: render_models_doc(config, root),
        DOC_ENDPOINTS: render_endpoints_doc(config, root),
        DOC_ERD: render_erd_doc(config, root),
        DOC_CONFIG: render_configuration_doc(config, root),
    }


@dataclass
class DocPlan:
    """One document file's current state versus freshly rendered state."""

    path: Path
    doc_name: str
    content: str
    status: str  # "new" | "changed" | "same"

    @property
    def needs_write(self) -> bool:
        """True when applying this plan would change disk contents."""
        return self.status != "same"

    def diff(self) -> str:
        """Return unified diff against existing on-disk file."""
        try:
            existing = self.path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        return compute_diff(existing, self.content, self.path.name)


def build_docs_plan(
    root: Optional[Path] = None,
    config: Optional[KairaConfig] = None,
    target_model: Optional[str] = None,
    only: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> list[DocPlan]:
    """Compare on-disk docs against freshly rendered projections."""
    root = Path.cwd() if root is None else root
    config = get_config() if config is None else config
    out_dir = output_dir if output_dir is not None else (root / "docs")

    if target_model:
        models_path = out_dir / DOC_MODELS
        existing = (
            models_path.read_text(encoding="utf-8") if models_path.is_file() else ""
        )
        targets: dict[tuple[Path, str], str] = {
            (out_dir / DOC_MODELS, DOC_MODELS): render_models_doc(
                config, root, target_model=target_model, existing_content=existing
            )
        }
    else:
        all_targets: dict[tuple[Path, str], str] = {
            (root / "README.md", "README.md (root)"): render_root_readme_doc(
                config, root
            ),
            (out_dir / DOC_README, f"docs/{DOC_README}"): render_readme_doc(
                config, root
            ),
            (out_dir / DOC_MODELS, f"docs/{DOC_MODELS}"): render_models_doc(
                config, root
            ),
            (out_dir / DOC_ENDPOINTS, f"docs/{DOC_ENDPOINTS}"): render_endpoints_doc(
                config, root
            ),
            (out_dir / DOC_ERD, f"docs/{DOC_ERD}"): render_erd_doc(config, root),
            (out_dir / DOC_CONFIG, f"docs/{DOC_CONFIG}"): render_configuration_doc(
                config, root
            ),
        }

        if only:
            only_norm = only.lower().strip()
            if only_norm in {"readme", "overview"}:
                targets = {
                    k: v for k, v in all_targets.items() if "README.md" in k[0].name
                }
            else:
                target_key = DOC_KEY_TO_FILE.get(only_norm, f"{only}.md")
                targets = {
                    k: v
                    for k, v in all_targets.items()
                    if k[0].name.lower() == target_key.lower()
                    and k[0].parent == out_dir
                }
                if not targets:
                    targets = {
                        k: v
                        for k, v in all_targets.items()
                        if target_key.lower() in k[1].lower()
                    }
        else:
            targets = all_targets

    plans: list[DocPlan] = []
    for (doc_path, display_name), content in targets.items():
        if not doc_path.is_file():
            status = "new"
        else:
            try:
                disk_content = doc_path.read_text(encoding="utf-8")
                clean_disk = re.sub(r'generated_at="[^"]+"', "", disk_content)
                clean_new = re.sub(r'generated_at="[^"]+"', "", content)
                status = "same" if clean_disk == clean_new else "changed"
            except OSError:
                status = "changed"
        plans.append(
            DocPlan(
                path=doc_path,
                doc_name=display_name,
                content=content,
                status=status,
            )
        )

    return plans


def is_docs_out_of_sync(root: Optional[Path] = None) -> bool:
    """True when generated documentation exists and is out of sync with project state."""
    root = Path.cwd() if root is None else root
    docs_dir = root / "docs"
    if not docs_dir.is_dir() or not (docs_dir / DOC_MODELS).is_file():
        return False
    plans = build_docs_plan(root)
    return any(p.needs_write for p in plans)


# ---------------------------------------------------------------------------
# Interactive Overwrite Flow (Phase 4 UX5)
# ---------------------------------------------------------------------------


def _prompt_action(plan: DocPlan) -> str:
    """Prompt user with [o] Overwrite [s] Skip [v] View full file."""
    try:
        import questionary

        choice = questionary.select(
            f"Action for {plan.path.name}:",
            choices=[
                {"name": "overwrite", "value": "o"},
                {"name": "skip", "value": "s"},
                {"name": "view full file", "value": "v"},
            ],
            default="o",
        ).ask()
        if choice in {"o", "s", "v"}:
            return str(choice)
    except Exception:
        pass

    console.print(
        Text.from_markup(
            "\n  [bold cyan]o[/bold cyan] Overwrite  "
            "[bold blue]s[/bold blue] Skip  "
            "[bold magenta]v[/bold magenta] View full file\n"
        )
    )
    return str(Prompt.ask("[bold]Action[/bold]", choices=["o", "s", "v"], default="o"))


def show_doc_diff(plan: DocPlan) -> None:
    """Display colored diff for a doc plan."""
    diff_text = plan.diff()
    if not diff_text.strip():
        return
    console.print(
        Panel(
            Syntax(diff_text, "diff", theme="monokai", line_numbers=True),
            title=f"[{Theme.PRIMARY}]Diff: {plan.path.name}[/{Theme.PRIMARY}]",
            border_style=Theme.BORDER_PRIMARY,
        )
    )


def apply_docs_plan(
    plans: list[DocPlan],
    *,
    force: bool = False,
    quiet: bool = False,
) -> tuple[int, int]:
    """Write the planned documentation files, prompting before overwrite.

    Returns:
        (written, skipped) counts.
    """
    written = 0
    skipped = 0

    for plan in plans:
        if not plan.needs_write:
            continue

        if plan.status == "new" or force or quiet or not is_interactive():
            plan.path.parent.mkdir(parents=True, exist_ok=True)
            plan.path.write_text(plan.content, encoding="utf-8")
            written += 1
            continue

        show_doc_diff(plan)
        while True:
            choice = _prompt_action(plan)
            if choice == "v":
                console.print(
                    Panel(
                        Syntax(
                            plan.content, "markdown", theme="monokai", line_numbers=True
                        ),
                        title=f"[{Theme.ACCENT}]Full file: {plan.path.name}[/{Theme.ACCENT}]",
                        border_style=Theme.ACCENT,
                    )
                )
                continue
            if choice == "o":
                plan.path.parent.mkdir(parents=True, exist_ok=True)
                plan.path.write_text(plan.content, encoding="utf-8")
                written += 1
            else:
                skipped += 1
            break

    return written, skipped


# ---------------------------------------------------------------------------
# Status Inspection
# ---------------------------------------------------------------------------


def get_docs_status(
    root: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> list[dict[str, str]]:
    """Return status records for all documentation files with full location and metadata."""
    root = Path.cwd() if root is None else root
    out_dir = output_dir if output_dir is not None else (root / "docs")
    plans = build_docs_plan(root, output_dir=out_dir)

    status_records: list[dict[str, str]] = []
    for plan in plans:
        # Determine relative path from root
        try:
            rel_str = str(plan.path.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel_str = plan.path.name

        if not plan.path.is_file():
            status_disp = "Missing"
            gen_at = "Never"
        elif plan.status == "same":
            status_disp = "Up to date"
            gen_at = (
                _extract_generated_at(plan.path.read_text(encoding="utf-8"))
                or "Recorded"
            )
        else:
            status_disp = "Stale (project changed)"
            gen_at = (
                _extract_generated_at(plan.path.read_text(encoding="utf-8"))
                or "Recorded"
            )

        meta = DOC_METADATA.get(rel_str, {})
        title = meta.get("title", plan.path.name)
        description = meta.get("description", plan.doc_name)
        location = meta.get("location", "Project")

        status_records.append(
            {
                "document": rel_str,
                "title": title,
                "description": description,
                "location": location,
                "path": str(plan.path),
                "status": status_disp,
                "generated_at": gen_at,
            }
        )

    return status_records


# ---------------------------------------------------------------------------
# Auto-Prompt Hook
# ---------------------------------------------------------------------------


def maybe_autodocs(*, quiet: bool = False, root: Optional[Path] = None) -> bool:
    """Prompt user to regenerate documentation after state-changing commands.

    Called by: generate model, sync model, add relation, auth add-guard, cache add.
    """
    root = Path.cwd() if root is None else root
    docs_dir = root / "docs"
    if not docs_dir.is_dir() or not (docs_dir / DOC_MODELS).is_file():
        return False

    plans = build_docs_plan(root)
    pending = [p for p in plans if p.needs_write]
    if not pending:
        return False

    names = ", ".join(p.path.name for p in pending)

    if quiet or not is_interactive():
        console.print(
            f"  [{Theme.MUTED}]Documentation is out of sync ({names}). "
            f"Run: kaira docs generate[/{Theme.MUTED}]"
        )
        return False

    console.print(
        f"\n  [{Theme.WARNING}]Documentation is out of sync[/{Theme.WARNING}] "
        f"[{Theme.MUTED}]({names})[/{Theme.MUTED}]"
    )
    answer = Prompt.ask(
        "  Regenerate?", choices=["y", "n"], default="y", show_choices=True
    )
    if answer.lower() != "y":
        console.print(
            f"  [{Theme.MUTED}]Skipped. Run `kaira docs generate` when ready.[/{Theme.MUTED}]"
        )
        return False

    written, _ = apply_docs_plan(pending, force=True)
    console.print(
        f"  [{Theme.SUCCESS}]Documentation regenerated[/{Theme.SUCCESS}] "
        f"[{Theme.MUTED}]({written} file{'s' if written != 1 else ''})[/{Theme.MUTED}]"
    )
    return True
