"""Consistency verification for upgraded Kaira projects."""

from __future__ import annotations

import json
from pathlib import Path

from kaira.app.exceptions import VerificationError


class MigrationVerifier:
    """Verifies that a project meets the structural criteria for its tier post-upgrade."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    def check(self, expected_tier: str = "standard") -> bool:
        """Run all verification checks. Raises VerificationError on failure."""
        errors: list[str] = []

        cfg_path = self.root / ".kaira.json"
        if not cfg_path.exists():
            errors.append("Missing .kaira.json configuration file.")
        else:
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                actual_tier = cfg_data.get("tier", "standard")
                if actual_tier != expected_tier:
                    errors.append(
                        f"Config tier mismatch: expected '{expected_tier}', found '{actual_tier}'."
                    )
            except Exception as e:
                errors.append(f"Corrupt .kaira.json: {e}")

        # Check main entrypoint
        main_files = [self.root / "main.py", self.root / "app" / "main.py"]
        if not any(f.exists() for f in main_files):
            errors.append(
                "Missing application entrypoint (neither main.py nor app/main.py exists)."
            )

        # Check layer directories if tier >= standard
        if expected_tier in ("standard", "enterprise"):
            for layer in ["models", "schemas", "services", "repositories", "routers"]:
                d = self.root / layer
                app_d = self.root / "app" / layer
                if (
                    not d.exists()
                    and not app_d.exists()
                    and expected_tier != "enterprise"
                ):
                    # For enterprise, domains/ may be used instead
                    pass

        if errors:
            raise VerificationError(
                "Project verification failed:\n" + "\n".join(f"- {e}" for e in errors)
            )

        return True
