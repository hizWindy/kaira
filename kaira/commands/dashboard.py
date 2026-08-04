"""Welcome dashboard for Kaira CLI — shown when kaira is run with no arguments."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path


from kaira.console import console
from kaira.core import ui
from kaira.core.progress import State


# ---------------------------------------------------------------------------
# Connection probe helpers
# ---------------------------------------------------------------------------


def _probe_db(db_type: str, timeout: float = 2.0) -> tuple[State, str]:
    """Attempt a lightweight TCP connection check for the configured database.

    Args:
        db_type: One of postgresql, mysql, mongodb, sqlite.
        timeout: Maximum seconds to wait for the connection.

    Returns:
        ``(state, detail)`` — the state drives the symbol and colour, the
        detail is the human-readable half of the step line.
    """
    if db_type == "sqlite":
        return State.DONE, "local file"

    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    port = port_map.get(db_type)
    if port is None:
        return State.PENDING, "unknown engine"

    # Read DATABASE_URL from env to get host, fallback to localhost
    raw_url = os.environ.get("DATABASE_URL", "")
    host = "localhost"
    if raw_url:
        import re

        m = re.search(r"@([^:/]+)[:/]", raw_url)
        if m:
            host = m.group(1)

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return State.DONE, f"connected · {host}:{port}"
    except (OSError, socket.timeout):
        return State.FAILED, f"unreachable · {host}:{port}"
    except Exception:
        return State.PARTIAL, f"timed out · {host}:{port}"


def _count_files(directory: Path, pattern: str) -> int:
    """Count files matching a glob pattern in a directory.

    ``__init__.py`` is excluded: every scaffolded package has one, so counting
    it reports "2 models" for a project that has none.

    Args:
        directory: Directory to scan.
        pattern: Glob pattern.

    Returns:
        Number of matching files (0 if directory does not exist).
    """
    if not directory.exists():
        return 0
    return len([p for p in directory.glob(pattern) if p.name != "__init__.py"])


def _detect_ci(root: Path) -> str:
    """Identify the CI platform from files on disk.

    ``.kaira.json`` has no CI field, so reading one there always reported
    "none".  The scaffolded workflow file is the actual evidence.

    Args:
        root: Project root.

    Returns:
        Platform name, or ``"none"`` when no workflow is present.
    """
    if (root / ".github" / "workflows").is_dir():
        return "github"
    if (root / ".gitlab-ci.yml").exists():
        return "gitlab"
    if (root / "bitbucket-pipelines.yml").exists():
        return "bitbucket"
    return "none"


def _last_action() -> str:
    """Read the most recent command from .kaira/history.jsonl.

    Returns:
        Short display string of the last command, or ``"none"``.
    """
    history_path = Path.cwd() / ".kaira" / "history.jsonl"
    if not history_path.exists():
        return "none"
    try:
        lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            record = json.loads(lines[-1])
            cmd = record.get("command", "unknown")
            ts = record.get("timestamp", "")[:10]
            return f"{cmd} · {ts}" if ts else str(cmd)
    except Exception:
        pass
    return "none"


# ---------------------------------------------------------------------------
# Dashboard renderers
# ---------------------------------------------------------------------------


def _render_inside_project(config_path: Path) -> None:
    """Render the full project dashboard.

    Args:
        config_path: Path to the .kaira.json file.
    """
    # Load raw config for fields not in KairaConfig dataclass
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        ui.section("project")
        ui.step("config", ".kaira.json is malformed or unreadable", State.FAILED)
        ui.hint("kaira config show")
        return

    from kaira.config import KairaConfig

    try:
        cfg = KairaConfig.from_dict(raw)
    except Exception:
        cfg = KairaConfig()

    project_name = raw.get("project", raw.get("project_name", Path.cwd().name))
    db_type = raw.get("database", cfg.db_type)
    auth_type = raw.get("auth", cfg.auth_type)
    api_version = raw.get("api_version", cfg.api_version)

    output_root = Path.cwd() / cfg.output_dir
    ci_platform = _detect_ci(output_root)

    # Stats
    model_count = _count_files(output_root / cfg.models_dir, "*.py")
    router_count = _count_files(output_root / cfg.routers_dir, "*_router.py")
    test_count = _count_files(output_root / "tests", "test_*.py")

    # DB connection probe (non-blocking, 2s timeout)
    db_state, db_detail = _probe_db(db_type, timeout=2.0)

    # Resolved online/offline mode (Phase 6, Feature 4) — from .kaira.json,
    # the single resolved source; never re-probed here.
    db_name = raw.get("db_name", "") or cfg.db_name
    db_mode = raw.get("db_mode", "") or cfg.db_mode or "online"
    if db_mode == "offline" and db_state == State.DONE:
        db_state = State.PARTIAL

    # Auth status
    auth_dir = output_root / "auth"
    auth_status = (
        ("auth setup", "configured", State.DONE)
        if (auth_dir / "dependencies.py").exists()
        else ("auth setup", "not configured", State.FAILED)
    )

    # Docker status
    docker_status = (
        ("docker", "Dockerfile present", State.DONE)
        if (output_root / "Dockerfile").exists()
        else ("docker", "not configured", State.PENDING)
    )

    # Pending migrations (only for relational DBs)
    if db_type == "mongodb":
        migration_status = ("migrations", "n/a for mongodb", State.PENDING)
    elif (output_root / "alembic").exists():
        migration_status = ("migrations", "initialized", State.DONE)
    else:
        migration_status = ("migrations", "not initialized", State.PARTIAL)

    # Action-required items, as commands rather than sentences about commands
    actions: list[str] = []
    if db_type != "mongodb" and not (output_root / "alembic").exists():
        actions.append("kaira migrate init")
    if not (auth_dir / "dependencies.py").exists():
        actions.append("kaira auth generate --type jwt")
    if not (output_root / "Dockerfile").exists():
        actions.append("kaira docker init --with-compose")
    if router_count > test_count:
        actions.append("kaira test generate --all")

    # ── Configuration: settings the project was scaffolded with.  These are
    #    facts, not outcomes, so they carry no state symbol.
    ui.section(project_name, f"api {api_version}")
    ui.field("database", f"{db_type} · {db_name}" if db_name else db_type)
    ui.field("auth", auth_type)
    ui.field("ci", ci_platform)

    # ── Health: each of these has a verdict, so each gets a state symbol.
    console.print()
    ui.step("connection", f"{db_mode} · {db_detail}", db_state)
    ui.step(*auth_status)
    ui.step(*docker_status)
    ui.step(*migration_status)

    # ── Resources
    ui.section("resources")
    ui.field("models", str(model_count))
    ui.field("routers", str(router_count))
    ui.field("tests", str(test_count))
    ui.field("last action", _last_action())

    # ── Action-required, as commands the user can paste
    if actions:
        ui.section("action required")
        for action in actions:
            ui.hint(action)

    ui.section("next")
    ui.hint('kaira generate model <Name> --fields "field:type"')
    ui.hint("kaira status")
    ui.hint("kaira commands")
    console.print()
    _print_attribution_footer()


def _render_outside_project() -> None:
    """Render the minimal welcome body when outside a Kaira project."""
    ui.section("no project here", Path.cwd().name)
    ui.note("looked for", ".kaira.json in this directory")

    ui.section("next")
    ui.hint("kaira init <project-name>")
    ui.hint("kaira guide")
    ui.hint("kaira commands")
    console.print()
    _print_attribution_footer()


def _print_attribution_footer() -> None:
    """Print the single muted attribution line below the dashboard body."""
    from kaira.core.theme import GUTTER, Theme, attribution, sym

    bolt = sym("BOLT")
    console.print(
        f"{GUTTER}[{Theme.MUTED}]{bolt} Kaira · {attribution()}[/{Theme.MUTED}]"
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def welcome_dashboard() -> None:
    """Render the Kaira welcome dashboard.

    Inside a project: full stats, connection status, action-required items.
    Outside a project: minimal welcome pointing to kaira init and kaira guide.
    Never blocks or crashes — all errors handled gracefully.
    """
    from kaira.config import find_config_path

    try:
        config_path = find_config_path()
        if config_path.exists():
            _render_inside_project(config_path)
        else:
            _render_outside_project()
    except Exception as exc:
        # Last-resort fallback — never crash
        ui.section("project")
        ui.step("dashboard", str(exc).splitlines()[0][:60], State.FAILED)
        ui.hint("kaira config show")
