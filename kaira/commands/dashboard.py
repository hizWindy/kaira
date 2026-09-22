"""Welcome dashboard for Kaira CLI — shown when kaira is run with no arguments.

This is the surface a developer lands on most often, and the one they read for
the least time: the question is almost always "where is this project up to",
not "tell me everything about it".  So the body is composed as an overview —
a headline naming the project and its connection state, a meter answering how
much of the setup is done, then the detail behind that meter — rather than as
a report to be read top to bottom.

The whole body is composed into a list of lines *before* anything is printed,
and handed to :func:`kaira.core.motion.reveal`.  That is what lets a live
terminal cascade it into place while a pipe, a CI log, or ``--quiet`` receives
the identical text all at once: the animation is a property of the printing,
never of the content.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

from kaira.console import console
from kaira.core import motion, ui
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
    except (TimeoutError, OSError):
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


def _server_line() -> tuple[State, str] | None:
    """Return the dev server's state and address, or ``None`` when it is down.

    Reported from the runtime record rather than by probing 8000, because the
    server may have been shifted off it — see :mod:`kaira.core.ports`.  A
    dashboard that says "not running" while the server runs on 8001 is worse
    than one that says nothing.
    """
    from kaira.core.ports import read_server

    recorded = read_server()
    if recorded is None:
        return None
    host, port = recorded
    return State.DONE, f"http://{host}:{port}"


# ---------------------------------------------------------------------------
# Dashboard composition
#
# Every ``_compose_*`` returns lines and prints nothing, so the caller decides
# how they reach the screen.
# ---------------------------------------------------------------------------


def _compose_inside_project(config_path: Path) -> list[str]:
    """Compose the full project dashboard.

    Args:
        config_path: Path to the .kaira.json file.

    Returns:
        The body as markup lines, in print order.
    """
    # Load raw config for fields not in KairaConfig dataclass
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return [
            *ui.fmt_section("project"),
            ui.fmt_step(
                "config", ".kaira.json is malformed or unreadable", State.FAILED
            ),
            ui.fmt_hint("kaira config show"),
        ]

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
    auth_ready = (auth_dir / "dependencies.py").exists()
    docker_ready = (output_root / "Dockerfile").exists()
    migrations_ready = (output_root / "alembic").exists()
    tests_ready = router_count == 0 or test_count >= router_count

    # Pending migrations (only for relational DBs)
    if db_type == "mongodb":
        migration_status = ("migrations", "n/a for mongodb", State.PENDING)
    elif migrations_ready:
        migration_status = ("migrations", "initialized", State.DONE)
    else:
        migration_status = ("migrations", "not initialized", State.PARTIAL)

    # ── Setup meter: the checklist behind it is exactly the checklist that
    #    produces the action-required list below, so the fraction and the
    #    commands can never disagree about what is outstanding.
    checklist: list[tuple[bool, str]] = [
        (db_state == State.DONE, ""),
        (auth_ready, "kaira auth generate --type jwt"),
        (docker_ready, "kaira docker init --with-compose"),
        (db_type == "mongodb" or migrations_ready, "kaira migrate init"),
        (tests_ready, "kaira test generate --all"),
    ]
    done_count = sum(1 for ok, _ in checklist if ok)
    actions = [command for ok, command in checklist if not ok and command]

    # ── Headline: what this project is, and whether it is reachable right now.
    #    The pill takes its colour from the same db_state the connection step
    #    below reports, so the two cannot contradict each other; the hollow dot
    #    is what distinguishes "configured" from "actually up".
    lines: list[str] = [""]
    lines.append(
        ui.fmt_headline(
            project_name,
            ui.fmt_pill(db_mode, db_state, filled=db_state == State.DONE),
        )
    )
    meta = f"api {api_version} · {db_type}"
    if db_name:
        meta += f" · {db_name}"
    lines.append(ui.fmt_caption(meta))

    # ── The meter summarises the list directly beneath it, so the two are one
    #    block: a blank line between them would read as two unrelated facts.
    lines.append("")
    lines.append(ui.fmt_meter(done_count, len(checklist), "setup"))
    lines.append(ui.fmt_step("connection", f"{db_mode} · {db_detail}", db_state))
    # The auth type is named whether or not it is wired up: "not configured"
    # alone leaves the reader guessing what it is not configured *as*.
    auth_detail = "configured" if auth_ready else "not configured"
    if auth_type and auth_type != "none":
        auth_detail = f"{auth_type} · {auth_detail}"
    lines.append(
        ui.fmt_step(
            "auth setup",
            auth_detail,
            State.DONE if auth_ready else State.FAILED,
        )
    )
    lines.append(
        ui.fmt_step(
            "docker",
            "Dockerfile present" if docker_ready else "not configured",
            State.DONE if docker_ready else State.PENDING,
        )
    )
    lines.append(ui.fmt_step(*migration_status))
    lines.append(
        ui.fmt_step(
            "ci",
            ci_platform,
            State.DONE if ci_platform != "none" else State.PENDING,
        )
    )
    server = _server_line()
    if server is not None:
        lines.append(ui.fmt_step("server", server[1], server[0]))

    # ── Resources
    lines.extend(ui.fmt_section("resources"))
    lines.append(
        ui.fmt_stats(
            [
                ("models", str(model_count)),
                ("routers", str(router_count)),
                ("tests", str(test_count)),
            ]
        )
    )
    lines.append(ui.fmt_field("last action", _last_action()))

    # ── Action-required, as commands the user can paste
    if actions:
        lines.extend(ui.fmt_section("action required"))
        lines.extend(ui.fmt_hint(action) for action in actions)

    lines.extend(ui.fmt_section("next"))
    lines.append(ui.fmt_hint('kaira generate model <Name> --fields "field:type"'))
    lines.append(ui.fmt_hint("kaira run"))
    lines.append(ui.fmt_hint("kaira commands"))
    lines.append("")
    lines.append(_attribution_line())
    return lines


def _compose_outside_project() -> list[str]:
    """Compose the minimal welcome body used outside a Kaira project."""
    return [
        "",
        ui.fmt_headline(
            "no project here",
            ui.fmt_pill(Path.cwd().name, State.PENDING, filled=False),
        ),
        ui.fmt_caption("this directory has no .kaira.json"),
        *ui.fmt_section("next"),
        ui.fmt_hint("kaira init <project-name>"),
        ui.fmt_hint("kaira guide"),
        ui.fmt_hint("kaira commands"),
        "",
        _attribution_line(),
    ]


def _attribution_line() -> str:
    """Return the single muted attribution line shown below the body."""
    from kaira.core.theme import GUTTER, Theme, attribution, sym

    bolt = sym("BOLT")
    return f"{GUTTER}[{Theme.MUTED}]{bolt} Kaira · {attribution()}[/{Theme.MUTED}]"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def welcome_dashboard() -> None:
    """Render the Kaira welcome dashboard.

    Inside a project: setup meter, health, stats, action-required items.
    Outside a project: minimal welcome pointing to kaira init and kaira guide.
    Never blocks or crashes — all errors handled gracefully.
    """
    from kaira.config import find_config_path

    try:
        config_path = find_config_path()
        lines = (
            _compose_inside_project(config_path)
            if config_path.exists()
            else _compose_outside_project()
        )
    except Exception as exc:
        # Last-resort fallback — never crash
        lines = [
            *ui.fmt_section("project"),
            ui.fmt_step("dashboard", str(exc).splitlines()[0][:60], State.FAILED),
            ui.fmt_hint("kaira config show"),
        ]

    # The sink is passed explicitly rather than left to the motion layer's
    # default, so this module's console remains the one thing that decides
    # where the dashboard lands.
    motion.reveal(lines, printer=console.print)
