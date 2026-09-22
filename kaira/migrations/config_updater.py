"""Configuration updater for project upgrades."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigUpdater:
    """Safely updates .kaira.json settings during migrations."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()
        self.config_path = self.root / ".kaira.json"

    def update_tier(self, new_tier: str, **extra_fields: Any) -> dict[str, Any]:
        """Update the tier and any optional extra attributes in .kaira.json."""
        data: dict[str, Any] = {}
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["tier"] = new_tier
        data.update(extra_fields)

        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return data
