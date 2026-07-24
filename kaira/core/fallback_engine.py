"""Kaira fallback engine — renders core/fallback.py into the user's project.

This module is part of the Kaira CLI (not the user's app).  It renders
the ``fallback_core.py.j2`` template into ``<output_dir>/core/fallback.py``
in the user's project when ``kaira cloud fallback enable`` is run.

The generated file contains:
- FallbackMode enum (CLOUD, DEGRADED, RECOVERED)
- Health probe loop (async, configurable interval)
- Write queue (append-only, fsync-safe, 0600 perms)
- Read routing per provider (SQLite mirror / JSON cache)
- Idempotent replay with conflict detection
- X-Kaira-Mode response header injection
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def generate_fallback_module(provider: str) -> Path:
    """Render ``fallback_core.py.j2`` into the user project's core directory.

    Args:
        provider: Cloud provider name ('supabase' | 'atlas' | 'firebase').

    Returns:
        Path to the generated ``core/fallback.py`` file.

    Raises:
        FileNotFoundError: If the template file is missing.
        OSError: If the output directory cannot be created or written.
    """
    from devflow.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    core_dir = output_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)

    # Ensure core/__init__.py exists
    init_py = core_dir / "__init__.py"
    if not init_py.exists():
        init_py.touch()

    env = Environment(  # nosec B701 — autoescape not needed for Python code generation
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    tmpl = env.get_template("fallback_core.py.j2")
    context = {
        "provider": provider,
        "local_engine": _local_engine_for(provider),
        "probe_interval": 30,
    }
    rendered = tmpl.render(**context)

    out_path = core_dir / "fallback.py"
    out_path.write_text(rendered, encoding="utf-8")

    return out_path


def _local_engine_for(provider: str) -> str:
    """Return the local fallback engine identifier for a cloud provider.

    Args:
        provider: Cloud provider name.

    Returns:
        Engine identifier string used inside the rendered template.
    """
    return {
        "supabase": "sqlite",
        "atlas": "mongodb_local",
        "firebase": "json_cache",
    }.get(provider, "json_cache")
