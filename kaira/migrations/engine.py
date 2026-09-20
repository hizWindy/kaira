"""MigrationEngine orchestrating tier upgrades with snapshot and rollback safety."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from kaira.app.exceptions import UpgradeError
from kaira.migrations.config_updater import ConfigUpdater
from kaira.migrations.file_writer import FileWriter
from kaira.migrations.main_updater import MainUpdater
from kaira.migrations.rollback import SnapshotManager
from kaira.migrations.rules import describe_upgrade, is_valid_upgrade
from kaira.migrations.verifier import MigrationVerifier


class MigrationEngine:
    """Executes tier upgrades, feature additions, and microservice decompositions."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or Path.cwd()
        self.config_updater = ConfigUpdater(self.root)
        self.file_writer = FileWriter(self.root)
        self.main_updater = MainUpdater(self.root)
        self.snapshot_mgr = SnapshotManager(self.root / ".kaira" / "backup")
        self.verifier = MigrationVerifier(self.root)

    def get_current_tier(self) -> str:
        cfg_path = self.root / ".kaira.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("tier", "standard")
            except Exception:
                pass
        return "standard"

    def get_project_name(self) -> str:
        cfg_path = self.root / ".kaira.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("db_name") or self.root.name
            except Exception:
                pass
        return self.root.name

    def upgrade(
        self,
        target_tier: str,
        dry_run: bool = False,
        features: Optional[List[str]] = None,
    ) -> List[str]:
        """Execute project upgrade to target_tier with full rollback on error."""
        current_tier = self.get_current_tier()
        target = target_tier.lower()

        if current_tier == target and not features:
            return [f"Project is already on tier '{target}'."]

        if not is_valid_upgrade(current_tier, target) and current_tier != target:
            raise UpgradeError(
                f"Invalid upgrade path: cannot upgrade from '{current_tier}' to '{target}'."
            )

        actions = describe_upgrade(current_tier, target)
        if features:
            for f in features:
                actions.append(f"Add feature: {f}")

        if dry_run:
            return actions

        # Create rollback snapshot before modifying any files
        self.snapshot_mgr.create_snapshot(self.root)

        project_name = self.get_project_name()

        try:
            # 1. Ensure layer directories exist
            self.file_writer.ensure_layer_directories()

            # 2. Update main.py to KhairaApp
            self.main_updater.upgrade_to_kaira_app(project_name, tier=target)

            # 3. Generate standard docs if missing
            self.file_writer.write_standard_docs(project_name)

            # 4. Handle enterprise specific scaffolds
            if target == "enterprise":
                (self.root / "domains").mkdir(parents=True, exist_ok=True)
                (self.root / "domains" / "__init__.py").touch(exist_ok=True)

            # 5. Update .kaira.json configuration
            self.config_updater.update_tier(target)

            # 6. Verify integrity of the upgrade
            self.verifier.check(expected_tier=target)

        except Exception as e:
            # Revert everything if anything failed
            self.snapshot_mgr.rollback(self.root)
            raise UpgradeError(
                f"Upgrade failed and was cleanly rolled back: {e}"
            ) from e

        return actions
