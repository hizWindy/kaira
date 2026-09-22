"""Snapshot creation and rollback engine for safe project upgrades."""

from __future__ import annotations

import shutil
from pathlib import Path

from kaira.app.exceptions import RollbackError


class SnapshotManager:
    """Manages project backups and restoration."""

    def __init__(self, backup_dir: Path | None = None) -> None:
        self.backup_dir = backup_dir or Path(".kaira/backup")

    def create_snapshot(self, root: Path | None = None) -> Path:
        """Create a backup of the project state before applying modifications."""
        root = root or Path.cwd()
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Clear existing backup directory contents
        for item in self.backup_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Backup configuration and code files
        items_to_save = [
            ".kaira.json",
            "main.py",
            "requirements.txt",
            "pyproject.toml",
            "alembic.ini",
        ]
        for name in items_to_save:
            src = root / name
            if src.exists():
                shutil.copy2(src, self.backup_dir / name)

        # Backup core directories if they exist
        for dir_name in [
            "app",
            "models",
            "schemas",
            "services",
            "repositories",
            "routers",
            "docs",
        ]:
            src_dir = root / dir_name
            if src_dir.exists() and src_dir.is_dir():
                shutil.copytree(src_dir, self.backup_dir / dir_name)

        return self.backup_dir

    def rollback(self, root: Path | None = None) -> None:
        """Restore project state from snapshot."""
        root = root or Path.cwd()
        if not self.backup_dir.exists():
            raise RollbackError(
                f"Cannot rollback: snapshot directory {self.backup_dir} does not exist."
            )

        try:
            for item in self.backup_dir.iterdir():
                target = root / item.name
                if item.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
        except Exception as e:
            raise RollbackError(f"Failed to restore project from snapshot: {e}") from e
