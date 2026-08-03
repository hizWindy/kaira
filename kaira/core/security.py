"""The single exclusion list for data that must never leave the database.

Every export path — the ``kaira export`` CLI and the export endpoints Kaira
generates into a project — strips fields through this module. There is exactly
one list, so a marker added here closes the hole on both sides at once.

``kaira export add`` copies this file verbatim into ``<project>/core/security.py``
so the generated app strips fields with the same code, not a re-implementation.
That is why nothing here may import from :mod:`kaira` or from any third-party
package: the copy has to run inside a project that has never heard of Kaira.

The sibling rule for CLI *arguments* lives in
``kaira.commands.ux_helpers.redact_sensitive`` — that one redacts values written
to the history file, this one drops columns read out of a database.
"""

from __future__ import annotations

from typing import Any

# Substring markers, matched case-insensitively against the field name. Kept as
# substrings on purpose: ``reset_token``, ``user_api_key`` and ``password_hash``
# are all caught without anyone having to enumerate them.
SENSITIVE_FIELD_MARKERS: tuple[str, ...] = (
    "password",
    "hashed_password",
    "token",
    "secret",
    "api_key",
)


def is_sensitive_field(name: str) -> bool:
    """Whether a field name matches any sensitive marker.

    Args:
        name: Column, attribute or document-key name.

    Returns:
        True when the field must be withheld from every export.
    """
    lowered = name.lower()
    return any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


def strip_sensitive_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Remove any field whose name matches a sensitive marker.

    Args:
        row: One database row/document as a plain dict.

    Returns:
        A new dict with sensitive keys dropped. There is deliberately no
        opt-out parameter — a flag here would become a flag on the CLI.
    """
    return {k: v for k, v in row.items() if not is_sensitive_field(k)}


def safe_field_names(names: list[str]) -> list[str]:
    """Filter a list of field names down to the exportable ones.

    Used to narrow a reflected column list *before* a SELECT is built, so
    sensitive columns are never read out of the database in the first place.

    Args:
        names: Candidate field names.

    Returns:
        The names that survive :func:`is_sensitive_field`, order preserved.
    """
    return [n for n in names if not is_sensitive_field(n)]
