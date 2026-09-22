"""Rewriter for main.py entrypoints during tier upgrades."""

from __future__ import annotations

import re
from pathlib import Path


class MainUpdater:
    """Updates main.py to use KairaApp instead of raw FastAPI."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    def find_main(self) -> Path | None:
        for candidate in ["main.py", "app/main.py", "src/main.py"]:
            p = self.root / candidate
            if p.exists():
                return p
        return None

    def upgrade_to_kaira_app(self, project_name: str, tier: str = "standard") -> bool:
        main_path = self.find_main()
        if not main_path:
            # Create standard main.py if none exists
            main_path = self.root / "main.py"
            main_path.write_text(
                self._generate_kaira_app_main(project_name, tier), encoding="utf-8"
            )
            return True

        content = main_path.read_text(encoding="utf-8")

        # If already using KairaApp, update tier if present
        if "KairaApp(" in content:
            updated = re.sub(r'tier=["\']\w+["\']', f'tier="{tier}"', content)
            main_path.write_text(updated, encoding="utf-8")
            return True

        # Convert app = FastAPI(...) to app = KairaApp(...)
        # Add import
        if (
            "from kaira.app import KairaApp" not in content
            and "from kaira import KairaApp" not in content
        ):
            content = "from kaira.app import KairaApp\n" + content

        # Replace instantiation
        pattern = r"app\s*=\s*FastAPI\([^)]*\)"
        replacement = f'app = KairaApp(\n    project_name="{project_name}",\n    tier="{tier}",\n    auto_register=True,\n    enforce_layers=True,\n)'
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content, count=1)
        else:
            content += f"\n\n# Upgraded by Khaira Framework\n{replacement}\n"

        main_path.write_text(content, encoding="utf-8")
        return True

    def _generate_kaira_app_main(self, project_name: str, tier: str) -> str:
        return f'''"""Application entry point powered by Khaira Framework."""

from __future__ import annotations

from kaira.app import KairaApp

app = KairaApp(
    project_name="{project_name}",
    tier="{tier}",
    auto_register=True,
    enforce_layers=True,
)

if __name__ == "__main__":
    app.run()
'''
