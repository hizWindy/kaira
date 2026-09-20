"""Kaira Upgrade & Migration Engine."""

from __future__ import annotations

from kaira.migrations.engine import MigrationEngine
from kaira.migrations.rollback import SnapshotManager
from kaira.migrations.rules import describe_upgrade, is_valid_upgrade
from kaira.migrations.verifier import MigrationVerifier

__all__ = [
    "MigrationEngine",
    "SnapshotManager",
    "MigrationVerifier",
    "is_valid_upgrade",
    "describe_upgrade",
]
