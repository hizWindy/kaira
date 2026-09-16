"""Kaira command aliases — single source of truth.

Aliases are additive shortcuts for high-frequency commands only.
They never appear in documentation, help text, or error messages;
the long form is always canonical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# The closed alias table
# ---------------------------------------------------------------------------

ALIASES: dict[str, list[str]] = {
    "g": ["generate", "model"],
    "gb": ["generate", "bulk"],
    "sm": ["sync", "model"],
    "mm": ["migrate", "make"],
    "mr": ["migrate", "run"],
    "st": ["status"],
    "up": ["docker", "up"],
    "dn": ["docker", "down"],
    "ds": ["docker", "status"],
    "q": ["quality"],
    "t": ["test", "run"],
    "?": ["menu"],
}

# ---------------------------------------------------------------------------
# The destructive blocklist — never aliased
# ---------------------------------------------------------------------------

DESTRUCTIVE_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("db", "reset"),
    ("db", "restore"),
    ("db", "switch"),
    ("migrate", "rollback"),
    ("seed", "clear"),
    ("env", "prune"),
    ("cache", "clear"),
    ("cloud", "disconnect"),
    ("cloud", "fallback"),
    ("docker", "down", "--volumes"),
    ("deploy", "run"),
)

# ---------------------------------------------------------------------------
# Registered guide topics for completion
# ---------------------------------------------------------------------------

GUIDE_TOPICS: tuple[str, ...] = (
    "init",
    "generate",
    "auth",
    "migrate",
    "security",
    "test",
    "docker",
    "ci",
    "env",
    "db",
    "config",
    "deps",
    "cache",
    "task",
    "integrate",
    "api",
    "quality",
    "deploy",
    "flags",
    "health-endpoint",
    "cloud",
    "fallback",
    "menu",
    "sync",
    "db-provision",
    "offline",
    "export",
    "commands",
    "monitor",
    "docs",
    "shortcuts",
)


# ---------------------------------------------------------------------------
# Resolution helper
# ---------------------------------------------------------------------------


def resolve_alias(token: str) -> list[str] | None:
    """Return the expanded token list for *token*, or None if not an alias."""
    expansion = ALIASES.get(token)
    return list(expansion) if expansion is not None else None


def resolve_argv(argv: list[str]) -> tuple[list[str], bool]:
    """Rewrite argv[1] if it matches an alias in ALIASES.

    Only argv[1] is ever consulted. Aliases are not recursive and never appear
    in a subcommand position.

    Args:
        argv: The argument list (e.g. sys.argv).

    Returns:
        tuple[list[str], bool]: (rewritten_argv, was_aliased)
    """
    if len(argv) > 1:
        expansion = resolve_alias(argv[1])
        if expansion is not None:
            return [argv[0]] + expansion + argv[2:], True
    return list(argv), False


def is_destructive_command(tokens: list[str]) -> bool:
    """Return True if *tokens* matches or starts with a destructive blocklist command."""
    for destructive in DESTRUCTIVE_COMMANDS:
        if (
            len(tokens) >= len(destructive)
            and tuple(tokens[: len(destructive)]) == destructive
        ):
            return True
    return False


def tokens_to_args_dict(expansion: list[str], remaining: list[str]) -> dict[str, str]:
    """Convert remaining command tokens into a key-value dictionary for history logging."""
    args_dict: dict[str, str] = {}
    pos_names: list[str] = []
    if expansion in (["generate", "model"], ["sync", "model"], ["test", "generate"]):
        pos_names = ["model"]
    elif expansion == ["generate", "bulk"]:
        pos_names = ["file"]
    elif expansion == ["migrate", "make"]:
        pos_names = ["message"]

    pos_idx = 0
    i = 0
    while i < len(remaining):
        tok = remaining[i]
        if tok.startswith("--"):
            if "=" in tok:
                k, v = tok[2:].split("=", 1)
                args_dict[k] = v
            elif i + 1 < len(remaining) and not remaining[i + 1].startswith("-"):
                args_dict[tok[2:]] = remaining[i + 1]
                i += 1
            else:
                args_dict[tok[2:]] = "true"
        elif tok.startswith("-"):
            flag = tok.lstrip("-")
            if i + 1 < len(remaining) and not remaining[i + 1].startswith("-"):
                args_dict[flag] = remaining[i + 1]
                i += 1
            else:
                args_dict[flag] = "true"
        else:
            key = pos_names[pos_idx] if pos_idx < len(pos_names) else f"arg{pos_idx}"
            args_dict[key] = tok
            pos_idx += 1
        i += 1
    return args_dict


# ---------------------------------------------------------------------------
# Dynamic completion callbacks (<50ms, fail-silent, no network, no DB)
# ---------------------------------------------------------------------------


def complete_model_name(
    ctx: Any = None,
    args: list[str] | None = None,
    incomplete: str = "",
) -> list[str]:
    """Complete model names dynamically from .kaira.json.

    Never opens a DB connection, makes an HTTP request, raises or prints.
    Returns [] silently on any error or if .kaira.json is missing/malformed.
    """
    try:
        current = Path.cwd()
        config_path: Path | None = None
        for directory in (current, *current.parents):
            candidate = directory / ".kaira.json"
            if candidate.is_file():
                config_path = candidate
                break
        if config_path is None:
            return []

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return []

        raw_models = data.get("generated_models", [])
        if not isinstance(raw_models, list):
            return []

        names: list[str] = [
            str(m["name"]) for m in raw_models if isinstance(m, dict) and m.get("name")
        ]
        if incomplete:
            return [n for n in names if n.lower().startswith(incomplete.lower())]
        return names
    except Exception:
        return []


def complete_guide_topic(
    ctx: Any = None,
    args: list[str] | None = None,
    incomplete: str = "",
) -> list[str]:
    """Complete guide topics from the registered topic list."""
    try:
        if incomplete:
            return [t for t in GUIDE_TOPICS if t.lower().startswith(incomplete.lower())]
        return list(GUIDE_TOPICS)
    except Exception:
        return []
