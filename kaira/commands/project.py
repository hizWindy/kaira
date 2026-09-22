"""Project init command — scaffold a full FastAPI project structure with database & auth wizards."""

from __future__ import annotations

import os
import re
import shutil
import sys
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Sequence

import typer
from jinja2 import Environment, FileSystemLoader
from rich.markup import escape


from kaira.config import KairaConfig
from kaira.console import console
from kaira.core import docker_render, docker_state, ui
from kaira.core.detector import write_with_check
from kaira.core.progress import (
    ProgressItem,
    ProgressPhase,
    ProgressRenderer,
    State,
    format_elapsed,
    format_size,
    state_symbol,
)
from kaira.core.theme import GUTTER, Theme, sym

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Try importing questionary for terminal select wizard
try:
    import questionary
except ImportError:
    questionary = None  # type: ignore[assignment]


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _elapsed_since(start: float) -> str:
    """Return the time since *start* (a ``time.monotonic()`` reading)."""
    return format_elapsed(time.monotonic() - start)


def _pascal_to_slug(name: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def select_option(message: str, choices: list[str], default: str) -> str:
    """Helper to select an option via questionary or fallback to text selection."""
    if questionary is not None:
        try:
            val = questionary.select(
                message, choices=choices, default=default, qmark=f"{GUTTER}?"
            ).ask()
            if val is not None:
                return val
        except Exception:
            pass

    # Fallback interactive selection
    console.print(f"\n{GUTTER}[{Theme.PRIMARY}]?[/{Theme.PRIMARY}] {message}")
    for i, choice in enumerate(choices, 1):
        indicator = "  "
        if choice == default:
            indicator = f"{sym('POINTER')} "
        console.print(f"{GUTTER}  {indicator}{i}) {choice}")

    while True:
        val = typer.prompt(f"Select option (1-{len(choices)})", default="1")
        try:
            idx = int(val) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        console.print("[red]Invalid selection. Try again.[/red]")


def select_confirm(message: str, default: bool = True) -> bool:
    """Helper to ask a yes/no question."""
    if questionary is not None:
        try:
            val = questionary.confirm(
                message, default=default, qmark=f"{GUTTER}?"
            ).ask()
            if val is not None:
                return val
        except Exception:
            pass
    return typer.confirm(f"{GUTTER}? {message}", default=default)


# ---------------------------------------------------------------------------
# Installer output parsing
#
# Raw installer output is never rendered.  It is parsed here into phase/item
# state transitions and, on failure, mapped to a short reason plus
# copy-pasteable fix commands.
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# uv
_UV_RESOLVED_RE = re.compile(r"^Resolved (\d+) package")
_UV_PREPARED_RE = re.compile(r"^Prepared (\d+) package")
_UV_INSTALLED_RE = re.compile(r"^Installed (\d+) package")
_UV_AUDITED_RE = re.compile(r"^Audited (\d+) package")
_UV_ADDED_RE = re.compile(r"^\+\s*([A-Za-z0-9._-]+)==(\S+)")

# pip
_PIP_DOWNLOADING_RE = re.compile(r"^\s*Downloading\s+\S+")
_PIP_INSTALLING_RE = re.compile(r"^Installing collected packages:")
_PIP_SUCCESS_RE = re.compile(r"^Successfully installed\s+(.+)$")
_PIP_SUCCESS_ITEM_RE = re.compile(r"^(.+)-([0-9][^-]*)$")

#: Byte sizes reported by pip, e.g. ``(18.2 MB)``.
_SIZE_RE = re.compile(r"\((\d+(?:\.\d+)?)\s*([kKMG]?B)\)")

_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


class _InstallOutputParser:
    """Drive phase and item states from an installer's streamed output.

    The parser only reacts to statements the installer actually makes.  When a
    package's completion cannot be determined from the output it is left
    pending until the batch finishes, rather than guessed mid-flight.
    """

    def __init__(
        self,
        strategy: str,
        resolve: "ProgressPhase",
        download: "ProgressPhase",
        install: "ProgressPhase",
    ) -> None:
        self.strategy = strategy
        self.resolve = resolve
        self.download = download
        self.install = install
        self.downloaded_bytes = 0.0

    # -- helpers ------------------------------------------------------------

    def _item(self, name: str) -> Optional["ProgressItem"]:
        """Find the nested item for *name*, comparing normalised names."""
        wanted = name.replace("_", "-").lower()
        for item in self.install.items:
            if item.name.replace("_", "-").lower() == wanted:
                return item
        return None

    def _advance_to_download(self) -> None:
        """Close the resolve phase and open download."""
        if self.resolve.state == State.ACTIVE:
            self.resolve.finish(
                self.resolve.summary or f"{len(self.install.items)} packages"
            )
        if self.download.state == State.PENDING:
            self.download.start()

    def _advance_to_install(self) -> None:
        """Close resolve/download and open install."""
        self._advance_to_download()
        if self.download.state == State.ACTIVE:
            summary = (
                format_size(self.downloaded_bytes)
                if self.downloaded_bytes
                else "cached"
            )
            self.download.finish(summary)
        if self.install.state == State.PENDING:
            self.install.start()

    # -- feed ---------------------------------------------------------------

    def feed(self, raw_line: str) -> bool:
        """Consume one output line.  Returns True when state changed."""
        line = _ANSI_RE.sub("", raw_line).strip()
        if not line:
            return False

        size_match = _SIZE_RE.search(line)
        if size_match:
            value, unit = size_match.groups()
            self.downloaded_bytes += float(value) * _SIZE_UNITS.get(unit.upper(), 1)

        # ── uv ────────────────────────────────────────────────────────────
        match = _UV_RESOLVED_RE.match(line)
        if match:
            self.resolve.summary = f"{match.group(1)} packages"
            self._advance_to_download()
            return True

        match = _UV_PREPARED_RE.match(line)
        if match:
            self._advance_to_install()
            return True

        match = _UV_AUDITED_RE.match(line)
        if match:
            self._advance_to_install()
            return True

        match = _UV_INSTALLED_RE.match(line)
        if match:
            return True

        match = _UV_ADDED_RE.match(line)
        if match:
            item = self._item(match.group(1))
            if item is not None:
                item.done(version=match.group(2))
                return True
            return False

        # ── pip ───────────────────────────────────────────────────────────
        if _PIP_DOWNLOADING_RE.match(line):
            self._advance_to_download()
            return True

        if _PIP_INSTALLING_RE.match(line):
            self._advance_to_install()
            return True

        match = _PIP_SUCCESS_RE.match(line)
        if match:
            for token in match.group(1).split():
                name_version = _PIP_SUCCESS_ITEM_RE.match(token)
                if not name_version:
                    continue
                item = self._item(name_version.group(1))
                if item is not None:
                    item.done(version=name_version.group(2))
            return True

        return False

    def finalize(self, success: bool) -> None:
        """Resolve any phase the installer never announced.

        On success every open phase closes cleanly.  On failure the phase that
        was still running is the one that broke, and later phases stay pending
        so the failure isolates to its own stage.
        """
        if success:
            self._advance_to_install()
            return

        for phase in (self.resolve, self.download, self.install):
            if phase.state == State.ACTIVE:
                phase.fail()
                return


#: Known failure signatures → (short reason, extra fix commands).
_INSTALL_ERROR_CASES: tuple[tuple[tuple[str, ...], str, tuple[str, ...]], ...] = (
    (
        ("pg_config executable not found", "libpq-fe.h"),
        "missing postgresql headers",
        ("sudo apt install libpq-dev",),
    ),
    (
        ("python.h: no such file",),
        "missing python headers",
        ("sudo apt install python3-dev",),
    ),
    (
        ("microsoft visual c++", "vcvarsall.bat"),
        "missing c++ build tools",
        ("install the Visual Studio C++ Build Tools",),
    ),
    (
        ("no matching distribution found", "could not find a version"),
        "no matching distribution",
        (),
    ),
    (
        ("resolutionimpossible", "conflicting dependencies", "version conflict"),
        "dependency conflict",
        (),
    ),
    (
        ("externally-managed-environment",),
        "environment is externally managed",
        ("kaira init --venv",),
    ),
    (
        ("no space left on device",),
        "no disk space left",
        (),
    ),
    (
        ("permission denied", "access is denied", "errno 13"),
        "permission denied",
        (),
    ),
    (
        (
            "temporary failure in name resolution",
            "failed to establish a new connection",
            "read timed out",
            "connection refused",
            "network is unreachable",
            "could not resolve host",
        ),
        "network unreachable",
        (),
    ),
    (
        ("failed to build",),
        "build failed",
        (),
    ),
)

_GENERIC_INSTALL_REASON = "install failed"


def classify_install_error(
    output: str, packages: Sequence[str]
) -> tuple[str, list[str]]:
    """Map raw installer output to a short reason and fix commands.

    The raw text is only ever inspected here — it is never rendered, so index
    URLs (which may carry credentials) and stack traces cannot leak into the
    terminal.  Unrecognised failures get a generic reason plus the
    ``kaira deps add`` hint rather than a dump of the output.

    Args:
        output: Combined installer stdout/stderr.
        packages: The package specs involved in the failure.

    Returns:
        ``(short_reason, fix_commands)``.
    """
    haystack = output.lower()
    reason = _GENERIC_INSTALL_REASON
    hints: list[str] = []

    for needles, mapped_reason, extra_hints in _INSTALL_ERROR_CASES:
        if any(needle in haystack for needle in needles):
            reason = mapped_reason
            hints = list(extra_hints)
            break

    for package in packages:
        base = re.split(r"[><=!\[,]", package)[0].strip()
        hint = f"kaira deps add {base}"
        if base and hint not in hints:
            hints.append(hint)
    return reason, hints


def install_packages(
    packages: list[str],
    project_dir: Optional[Path] = None,
    upgrade: bool = False,
) -> tuple[int, int, int]:
    """Install python packages via batched invocation with progress rendering.

    Uses ``uv`` if available on PATH, otherwise falls back to ``pip`` silently.
    The full package set is passed in a single invocation so the resolver can
    backtrack across the whole dependency graph; installing one package at a
    time can leave mutually incompatible versions installed.

    Phase transitions (resolve → download → install) and item states are driven
    by parsing the installer's actual output, never by timers or estimates.

    Args:
        packages: List of pip-format package specifiers.
        project_dir: Optional project directory for venv detection.
        upgrade: Pass ``--upgrade`` and skip the already-installed pre-check.

    Returns:
        tuple[int, int, int]: (installed_count, failed_count, skipped_count)
    """
    import importlib.metadata
    import importlib.util

    from kaira.config import get_venv_python

    python_exe = get_venv_python(project_dir)

    # Package → importable-name mapping
    pkg_import_map = {
        "fastapi": "fastapi",
        "fastapi[standard]": "fastapi",
        "uvicorn[standard]": "uvicorn",
        "sqlalchemy[asyncio]": "sqlalchemy",
        "alembic": "alembic",
        "pydantic": "pydantic",
        "pydantic-settings": "pydantic_settings",
        "slowapi": "slowapi",
        "loguru": "loguru",
        "python-jose[cryptography]": "jose",
        "passlib[bcrypt]": "passlib",
        "python-dotenv": "dotenv",
        "bcrypt": "bcrypt",
        "asyncpg": "asyncpg",
        "aiomysql": "aiomysql",
        "motor": "motor",
        "beanie": "beanie",
        "aiosqlite": "aiosqlite",
    }

    def _pkg_base(spec: str) -> str:
        """Extract bare package name from a pip spec."""
        return re.split(r"[><=!\[,]", spec)[0].strip()

    def _import_name(spec: str) -> str:
        """Resolve the import name for a package spec."""
        return pkg_import_map.get(spec, _pkg_base(spec))

    def _check_installed(spec: str) -> bool:
        """Check whether a package is already installed."""
        import_name = _import_name(spec)
        try:
            if python_exe != sys.executable:
                res = subprocess.run(
                    [
                        python_exe,
                        "-c",
                        (
                            "import importlib.metadata; "
                            f"print(importlib.metadata.version('{import_name.replace('_', '-')}'))"
                        ),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                if res.returncode == 0:
                    return True
                res_imp = subprocess.run(
                    [python_exe, "-c", f"import {import_name}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return res_imp.returncode == 0
            else:
                importlib.metadata.version(import_name.replace("_", "-"))
                return True
        except Exception:
            if python_exe == sys.executable:
                try:
                    return importlib.util.find_spec(import_name) is not None
                except Exception:
                    pass
            return False

    def _get_version(spec: str) -> str:
        """Get the installed version of a package, or empty string."""
        import_name = _import_name(spec)
        try:
            if python_exe != sys.executable:
                rv = subprocess.run(
                    [
                        python_exe,
                        "-c",
                        (
                            "import importlib.metadata; "
                            f"print(importlib.metadata.version('{import_name.replace('_', '-')}'))"
                        ),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                return rv.stdout.strip() if rv.returncode == 0 else ""
            else:
                return importlib.metadata.version(import_name.replace("_", "-"))
        except Exception:
            return ""

    # ── Pre-check: which packages are already installed ────────────────────
    to_install: list[str] = []
    skipped_count = 0

    if upgrade:
        # Upgrades always re-run the resolver — nothing is skipped.
        to_install = list(packages)
    else:
        for pkg in packages:
            if _check_installed(pkg):
                skipped_count += 1
            else:
                to_install.append(pkg)

    # ── Detect installer strategy (uv first, silent pip fallback) ──────────
    uv_bin = shutil.which("uv")
    strategy = "uv" if uv_bin else "pip"

    # ── Build progress renderer ────────────────────────────────────────────
    install_items = [ProgressItem(name=_pkg_base(p)) for p in to_install]

    resolve_phase = ProgressPhase(name="resolve")
    download_phase = ProgressPhase(name="download")
    install_phase = ProgressPhase(name="install", items=install_items)

    renderer = ProgressRenderer(
        title="updating" if upgrade else "installing",
        strategy=strategy,
        total=len(to_install),
        phases=[resolve_phase, download_phase, install_phase],
    )

    if not to_install:
        # Everything already present — report without running an installer.
        for phase, summary in (
            (resolve_phase, f"{skipped_count} packages"),
            (download_phase, "nothing to fetch"),
            (install_phase, f"{skipped_count} already installed"),
        ):
            phase.summary = summary
            phase.state = State.DONE
        renderer.print_result()
        return 0, 0, skipped_count

    # ── Run one batched invocation (never one package at a time) ───────────
    if uv_bin:
        cmd = [uv_bin, "pip", "install", "--python", python_exe]
        if upgrade:
            cmd.append("--upgrade")
        cmd.extend(to_install)
    else:
        cmd = [python_exe, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        cmd.extend(to_install)

    parser = _InstallOutputParser(
        strategy=strategy,
        resolve=resolve_phase,
        download=download_phase,
        install=install_phase,
    )

    with renderer:
        resolve_phase.start()
        renderer.refresh()

        raw_output: list[str] = []
        # pip block-buffers its output when stdout is a pipe, which would
        # bunch every phase marker up at the end and make the timings useless.
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            raw_output.append(raw_line)
            if parser.feed(raw_line):
                renderer.refresh()
        returncode = proc.wait()

        # Close out any phase the installer never announced.  On failure the
        # phase that was still running is the one that broke.
        parser.finalize(success=returncode == 0)
        combined_output = "".join(raw_output)
        installed_count = 0
        failed_count = 0
        fix_hints: list[str] = []

        if install_phase.state == State.PENDING:
            # The run died before installation started: the failure belongs to
            # resolve or download, so the install phase never expands.
            failed_count = len(install_items)
            reason, fix_hints = classify_install_error(combined_output, to_install)
            for phase in (resolve_phase, download_phase):
                if phase.state == State.FAILED:
                    phase.summary = reason
        else:
            for item in install_items:
                spec = next(
                    (p for p in to_install if _pkg_base(p) == item.name), item.name
                )
                version = _get_version(spec)
                # Exit 0 from a batched installer means every requested package
                # landed; otherwise trust only what is importable afterwards.
                if returncode == 0 or version:
                    item.done(version=item.version or version)
                    installed_count += 1
                    continue

                # Raw output is mapped to a short reason; it is never rendered.
                reason, hints = classify_install_error(combined_output, [item.name])
                item.fail(reason)
                failed_count += 1
                for hint in hints:
                    if hint not in fix_hints:
                        fix_hints.append(hint)

            install_phase.finish(
                f"{installed_count} ok · {failed_count} failed"
                if failed_count
                else f"{installed_count} packages"
            )
        renderer.refresh()

    renderer.print_result(fix_hints)
    return installed_count, failed_count, skipped_count


def init_project(
    name: str,
    db: str,
    auth: str,
    docker: bool,
    ci: str,
    cwd: Path,
    tier: str = "standard",
) -> None:
    """Scaffold a FastAPI project with tier configuration inside named directory."""
    env = _get_env()
    slug = _pascal_to_slug(name)

    # Ensure targeted folders exist
    PROJECT_DIRS = [
        "models",
        "repositories",
        "schemas",
        "services",
        "routers",
        "auth",
        "config",
        "core",
        "middleware",
        "logs",
        "tests",
    ]

    for d in PROJECT_DIRS:
        (cwd / d).mkdir(parents=True, exist_ok=True)
        (cwd / d / "__init__.py").touch(exist_ok=True)

    # Empty logkeep file
    (cwd / "logs" / ".gitkeep").touch(exist_ok=True)

    # Context values for Jinja render
    ctx = {
        "project_name": name,
        "project_slug": slug,
        "db_type": db,
        "auth_type": auth,
        "api_version": "v1",
        "tier": tier,
        "providers": ["cache", "auth", "monitor"] if tier == "enterprise" else ["cache", "auth"],
        "enforce_layers": True,
        "kaira_version": "0.2.4",
    }

    # 1. main.py selection based on tier
    if tier == "simple":
        main_tmpl = env.get_template("main_simple.py.j2")
    else:
        main_tmpl = env.get_template("main_app.py.j2")
    write_with_check(
        cwd / "main.py", main_tmpl.render(**ctx), force=True, non_interactive=True
    )

    # 2. config/settings.py
    settings_tmpl = env.get_template("env_settings.py.j2")
    write_with_check(
        cwd / "config" / "settings.py",
        settings_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 3. core/database.py
    if db == "mongodb":
        db_tmpl = env.get_template("database_mongodb.py.j2")
    else:
        db_tmpl = env.get_template("database_async.py.j2")
    write_with_check(
        cwd / "core" / "database.py",
        db_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 3b. core/db_mode.py — offline/online startup resolution (Phase 6, Feature 3)
    dbmode_tmpl = env.get_template("db_mode.py.j2")
    write_with_check(
        cwd / "core" / "db_mode.py",
        dbmode_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 3c. routers/health_router.py
    health_tmpl = env.get_template("health_router.py.j2")
    write_with_check(
        cwd / "routers" / "health_router.py",
        health_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 4. core/logger.py
    logger_tmpl = env.get_template("logger.py.j2")
    write_with_check(
        cwd / "core" / "logger.py",
        logger_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 5. middleware/security.py
    sec_tmpl = env.get_template("security_middleware.py.j2")
    write_with_check(
        cwd / "middleware" / "security.py",
        sec_tmpl.render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 6. rate_limit.py
    rl_tmpl = env.get_template("rate_limit.py.j2")
    write_with_check(
        cwd / "rate_limit.py", rl_tmpl.render(**ctx), force=True, non_interactive=True
    )

    # 7. auth boilerplate
    if auth == "jwt":
        templates = {
            "auth_jwt_dependencies.py.j2": cwd / "auth" / "dependencies.py",
            "auth_jwt_router.py.j2": cwd / "auth" / "router.py",
            "auth_jwt_service.py.j2": cwd / "auth" / "service.py",
            "auth_jwt_schemas.py.j2": cwd / "auth" / "schemas.py",
            "auth_jwt_utils.py.j2": cwd / "auth" / "utils.py",
            "auth_blacklisted_token_model.py.j2": cwd
            / "models"
            / "blacklisted_token.py",
        }
        for t_name, t_dest in templates.items():
            write_with_check(
                t_dest,
                env.get_template(t_name).render(**ctx),
                force=True,
                non_interactive=True,
            )
    elif auth == "oauth2":
        write_with_check(
            cwd / "auth" / "oauth2.py",
            env.get_template("auth_oauth2.py.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
    elif auth == "api-key":
        write_with_check(
            cwd / "auth" / "api_key.py",
            env.get_template("auth_api_key.py.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )

    # 8. Active environment file (.env). Staging/production config belongs in the
    # deploy platform's env/secrets, not committed files — so only .env (+ the
    # committed .env.example below) is generated.
    secret = "placeholder-32-character-secret-key-for-kaira-api"
    db_url = "sqlite+aiosqlite:///./app.db"
    if db == "postgresql":
        db_url = f"postgresql+asyncpg://user:pass@localhost:5432/{slug}"
    elif db == "mysql":
        db_url = f"mysql+aiomysql://user:pass@localhost:3306/{slug}"
    elif db == "mongodb":
        db_url = f"mongodb://localhost:27017/{slug}"

    # SQLite is zero-config: keep DATABASE_URL active so the app boots on a
    # fresh clone. Server-based DBs stay commented until credentials are set.
    if db == "sqlite":
        db_line = f"DATABASE_URL={db_url}\n"
    else:
        db_line = (
            f"# DATABASE_URL={db_url}\n"
            f"# Uncomment and fill in your real credentials before running the app.\n"
        )
    # Offline/Online contract (Phase 6, Feature 3). Offline store matches the
    # data-model family: SQLite for relational, local MongoDB for Mongo (§3.3).
    if db == "mongodb":
        offline_url = f"mongodb://localhost:27017/{slug}_offline"
    else:
        offline_url = "sqlite+aiosqlite:///./.kaira/offline.db"
    mode_lines = (
        f"DB_MODE=online\nOFFLINE_DATABASE_URL={offline_url}\nFALLBACK_MODE=off\n"
    )
    env_content = (
        f"APP_ENV=development\n"
        f"APP_NAME={name}\n"
        f"{db_line}"
        f"{mode_lines}"
        f"JWT_SECRET_KEY={secret}\n"
        f'ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n'
        f"DEBUG=True\n"
    )
    write_with_check(cwd / ".env", env_content, force=True, non_interactive=True)

    # env.example
    if db == "sqlite":
        example_db_line = "DATABASE_URL=sqlite+aiosqlite:///./app.db\n"
    else:
        example_db_line = (
            "# DATABASE_URL=<your database connection string>\n"
            "# Uncomment and fill in your real credentials before running the app.\n"
        )
    example_content = (
        "APP_ENV=development\n"
        f"APP_NAME={name}\n"
        f"{example_db_line}"
        f"{mode_lines}"
        "JWT_SECRET_KEY=your-minimum-32-character-secret-key-here\n"
        'ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n'
        "DEBUG=False\n"
    )
    write_with_check(
        cwd / ".env.example", example_content, force=True, non_interactive=True
    )

    # 9. Docker setup — rendered from the same dynamic registry `kaira docker
    # sync` uses, so a fresh project and a synced one produce identical output.
    # No .kaira.json exists yet at this point (written in step 12 below), so the
    # state is built directly from what init already knows rather than through
    # docker_state.resolve_state(), which reads it from disk.
    docker_python = docker_state.resolve_python_version(None)
    if docker:
        # Docker's slug must match what `docker sync` recomputes later from the
        # directory name via docker_state.resolve_state() — not the DB-name
        # slug above, which keeps hyphens `_pascal_to_slug` doesn't touch.
        # A mismatch here makes a freshly scaffolded project look drifted the
        # moment `kaira docker sync` runs against it.
        docker_project_state = docker_state.ProjectState(
            project_name=name,
            project_slug=docker_state.slugify_project_name(name),
            db_type=db,
            python_version=docker_python,
        )
        for filename, content in docker_render.render_files(
            docker_project_state, with_compose=True
        ).items():
            write_with_check(cwd / filename, content, force=True, non_interactive=True)

    # 10. CI/CD workflow setup
    if ci == "github":
        gh_dir = cwd / ".github" / "workflows"
        gh_dir.mkdir(parents=True, exist_ok=True)
        write_with_check(
            gh_dir / "test.yml",
            env.get_template("ci_github.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
        write_with_check(
            gh_dir / "security.yml",
            env.get_template("ci_github_security.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
        write_with_check(
            gh_dir / "deploy.yml",
            env.get_template("ci_github_deploy.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
    elif ci == "gitlab":
        write_with_check(
            cwd / ".gitlab-ci.yml",
            env.get_template("ci_gitlab.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )
    elif ci == "bitbucket":
        write_with_check(
            cwd / "bitbucket-pipelines.yml",
            env.get_template("ci_bitbucket.yml.j2").render(**ctx),
            force=True,
            non_interactive=True,
        )

    # 11. Gitignore, project README, pyproject.toml
    write_with_check(
        cwd / ".gitignore",
        env.get_template("gitignore_project.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )
    write_with_check(
        cwd / "README.md",
        env.get_template("readme_project.md.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )
    write_with_check(
        cwd / "AGENTS.md",
        env.get_template("agents_project.md.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 11b. Agent Skills Library (.agents/skills/*/SKILL.md)
    skills_dir = cwd / ".agents" / "skills"
    skill_definitions = [
        ("khaira-scaffold-model", "skills/skill_scaffold_model.md.j2"),
        ("khaira-sync-layers", "skills/skill_sync_layers.md.j2"),
        ("khaira-ai-agent", "skills/skill_ai_agent.md.j2"),
        ("khaira-quality-gate", "skills/skill_quality_gate.md.j2"),
        ("kaira-scaffold-model", "skills/skill_scaffold_model.md.j2"),
        ("kaira-sync-layers", "skills/skill_sync_layers.md.j2"),
        ("kaira-ai-agent", "skills/skill_ai_agent.md.j2"),
        ("kaira-quality-gate", "skills/skill_quality_gate.md.j2"),
    ]
    if db != "mongodb":
        skill_definitions.append(
            ("khaira-db-migrations", "skills/skill_db_migrations.md.j2")
        )
        skill_definitions.append(
            ("kaira-db-migrations", "skills/skill_db_migrations.md.j2")
        )

    for skill_name, tmpl_name in skill_definitions:
        target_dir = skills_dir / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)
        write_with_check(
            target_dir / "SKILL.md",
            env.get_template(tmpl_name).render(**ctx, skill_name=skill_name),
            force=True,
            non_interactive=True,
        )

    write_with_check(
        cwd / "pyproject.toml",
        env.get_template("pyproject_generated.toml.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )
    # requirements.txt — pinned mirror of pyproject deps for broad clone/deploy compat.
    write_with_check(
        cwd / "requirements.txt",
        env.get_template("requirements.txt.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )
    # Makefile — one-word onboarding (make install / db / migrate / dev).
    write_with_check(
        cwd / "Makefile",
        env.get_template("makefile.j2").render(**ctx),
        force=True,
        non_interactive=True,
    )

    # 12. Local Kaira settings configuration file
    config = KairaConfig(
        db_type=db,
        auth_type=auth,
        tier=tier,
        output_dir=".",
        docker_enabled=docker,
        docker_compose=docker,
        docker_python=docker_python if docker else "",
        providers=["cache", "auth", "monitor"] if tier == "enterprise" else ["cache", "auth"],
    )
    # Save config directly inside the project directory
    config_path = cwd / ".kaira.json"
    import json

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)

    # 13. Documentation generation for framework tiers
    if tier != "simple":
        try:
            from kaira.migrations.file_writer import FileWriter

            FileWriter(cwd).write_standard_docs(name)
        except Exception:
            pass


def init_command(
    name: Optional[str] = None,
    db: Optional[str] = None,
    auth: Optional[str] = None,
    docker: Optional[bool] = None,
    ci: Optional[str] = None,
    profile: Optional[str] = None,
    yes: bool = False,
    tier: Optional[str] = None,
    db_user: Optional[str] = None,
    db_password: Optional[str] = None,
    db_host: Optional[str] = None,
    db_port: Optional[int] = None,
) -> None:
    """Entrypoint for kaira init command with wizard setup."""
    valid_dbs = {"postgresql", "mysql", "mongodb", "sqlite"}
    valid_auth = {"jwt", "oauth2", "api-key", "none"}
    valid_ci = {"github", "gitlab", "bitbucket", "none"}
    valid_profiles = {"solo", "standard", "scale"}

    profile = (profile or "solo").lower()
    if profile not in valid_profiles:
        console.print(
            f"[red]Error: Unknown profile '{profile}'. Choose: {', '.join(sorted(valid_profiles))}.[/red]"
        )
        raise typer.Exit(1)

    # Check if we are inside a folder with existing kaira configuration
    # If project name is completely omitted, we trigger the wizard or prompt
    if not name:
        console.print("⚡ Khaira — New Project\n────────────────────────────────────")
        name = typer.prompt("Project name")
        # Validate project name
        if not re.match(r"^[a-z0-9-]+$", name):
            console.print(
                "[red]Error: Project name must be lowercase, hyphens allowed, no spaces.[/red]"
            )
            raise typer.Exit(1)
    else:
        # Validate project name argument
        if not re.match(r"^[a-z0-9-]+$", name):
            console.print(
                "[red]Error: Project name must be lowercase, hyphens allowed, no spaces.[/red]"
            )
            raise typer.Exit(1)

    project_dir = Path.cwd() / name
    if project_dir.exists():
        console.print(f"[red]Error: Folder '{name}' already exists.[/red]")
        raise typer.Exit(1)

    started = time.monotonic()

    in_tests = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    is_interactive_run = sys.stdin.isatty() and not yes and not in_tests

    # Interactive setup wizard.  A fully flag-driven run asks nothing, so the
    # heading would introduce an empty section — the scaffold section below
    # echoes the resolved configuration either way.
    if not (db and auth and docker is not None and ci is not None and tier is not None):
        ui.section("setup", name)

    if not tier:
        if is_interactive_run:
            tier_choice = select_option(
                "architecture tier",
                [
                    "Standard (Recommended: 5-Layer Pipeline with KairaApp)",
                    "Enterprise (5-Layer + Monitoring Probes + Metrics + Advanced Guards)",
                    "Simple (Lightweight single-file FastAPI)",
                ],
                "Standard (Recommended: 5-Layer Pipeline with KairaApp)",
            )
            if "enterprise" in tier_choice.lower():
                tier = "enterprise"
            elif "simple" in tier_choice.lower():
                tier = "simple"
            else:
                tier = "standard"
        else:
            tier = "standard"
    else:
        tier = tier.lower()

    if not db:
        db_choice = select_option(
            "database",
            ["SQLite", "PostgreSQL", "MySQL", "MongoDB"],
            "SQLite",
        )
        db = db_choice.lower()
    else:
        db = db.lower()
    if db not in valid_dbs:
        console.print(
            f"[red]Error: Unsupported database '{db}'. Choose: {', '.join(sorted(valid_dbs))}.[/red]"
        )
        raise typer.Exit(1)

    # Database credentials prompt for client-server DBMS
    if db in ("postgresql", "mysql"):
        default_user = "postgres" if db == "postgresql" else "root"
        default_port = 5432 if db == "postgresql" else 3306
        if is_interactive_run:
            if db_user is None:
                user_ans = select_option(f"{db} user", [default_user, "custom"], default_user)
                if user_ans == "custom":
                    from kaira.core import prompts
                    db_user = prompts.text(f"{db} username", default=default_user)
                else:
                    db_user = default_user
            if db_password is None:
                from kaira.core import prompts
                db_password = prompts.secret(f"{db} password (Enter if blank)")
            if db_host is None:
                db_host = "localhost"
            if db_port is None:
                db_port = default_port
        else:
            db_user = db_user or default_user
            db_host = db_host or "localhost"
            db_port = db_port or default_port

    if not auth:
        auth_choice = select_option("auth", ["JWT", "OAuth2", "API Key", "None"], "JWT")
        auth = auth_choice.lower().replace(" ", "-")
    else:
        auth = auth.lower().replace(" ", "-")
    if auth not in valid_auth:
        console.print(
            f"[red]Error: Unsupported auth type '{auth}'. Choose: {', '.join(sorted(valid_auth))}.[/red]"
        )
        raise typer.Exit(1)

    if docker is None:
        docker = select_confirm("docker", default=True)

    if ci is None:
        include_ci = select_confirm("ci/cd", default=True)
        if include_ci:
            ci_choice = select_option(
                "ci platform",
                ["GitHub Actions", "GitLab CI", "Bitbucket Pipelines"],
                "GitHub Actions",
            )
            if "github" in ci_choice.lower():
                ci = "github"
            elif "gitlab" in ci_choice.lower():
                ci = "gitlab"
            else:
                ci = "bitbucket"
        else:
            ci = "none"
    else:
        ci = (
            ci.lower()
            .replace("github-actions", "github")
            .replace("gitlab-ci", "gitlab")
            .replace("bitbucket-pipelines", "bitbucket")
        )
    if ci not in valid_ci:
        console.print(
            f"[red]Error: Unsupported CI platform '{ci}'. Choose: {', '.join(sorted(valid_ci))}.[/red]"
        )
        raise typer.Exit(1)

    # Echo the resolved configuration so a flag-driven run shows the same
    # summary an interactive one does.
    ui.section("scaffold")
    ui.field("tier", tier)
    ui.field("database", db)
    ui.field("auth", auth)
    ui.field("docker", "yes" if docker else "no")
    ui.field("ci", ci)
    console.print()

    # Scaffold the project files
    scaffold_started = time.monotonic()
    project_dir.mkdir(parents=True, exist_ok=True)
    init_project(name, db, auth, docker, ci, project_dir, tier=tier)
    ui.step("project files", _elapsed_since(scaffold_started))

    # Package installation phase
    # Determine DB-specific and Core required packages
    # Minimum-version (">=") pins so pip installs the newest wheel that fits the
    # user's Python (fresh wheels exist for 3.10–3.14+); upper caps only where the
    # next major would break generated code (beanie 2.0 drops motor; bcrypt 5.0
    # trips a passlib warning).
    req_packages = [
        "fastapi[standard]>=0.115.0",
        "uvicorn[standard]>=0.29.0",
        "pydantic>=2.9.0,<3.0.0",
        "pydantic-settings>=2.5.0,<3.0.0",
        "slowapi>=0.1.9",
        "loguru>=0.7.2",
        "python-dotenv>=1.0.1",
        "bcrypt>=4.1.2,<5.0.0",
        "python-jose[cryptography]>=3.3.0",
        "passlib[bcrypt]>=1.7.4",
    ]

    if db == "postgresql":
        req_packages.extend(
            ["sqlalchemy[asyncio]>=2.0.36,<3.0.0", "asyncpg>=0.30.0", "alembic>=1.14.0"]
        )
    elif db == "mysql":
        req_packages.extend(
            ["sqlalchemy[asyncio]>=2.0.36,<3.0.0", "aiomysql>=0.2.0", "alembic>=1.14.0"]
        )
    elif db == "mongodb":
        req_packages.extend(["motor>=3.3.0,<4.0.0", "beanie>=1.24.0,<2.0.0"])
    elif db == "sqlite":
        req_packages.extend(
            [
                "sqlalchemy[asyncio]>=2.0.36,<3.0.0",
                "aiosqlite>=0.20.0",
                "alembic>=1.14.0",
            ]
        )

    if os.environ.get("PYTEST_CURRENT_TEST"):
        ui.step("virtualenv", "skipped while running tests", State.PENDING)
        ui.step("dependencies", "skipped while running tests", State.PENDING)
    else:
        # Create virtual environment
        venv_started = time.monotonic()
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", ".venv"],
                cwd=project_dir,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            ui.step("virtualenv", f".venv · {_elapsed_since(venv_started)}")
        except Exception as e:
            ui.step("virtualenv", str(e).splitlines()[0][:60], State.FAILED)

        console.print()
        install_packages(req_packages, project_dir=project_dir)

    # ── Auto database provisioning (Phase 6, Feature 1) ───────────────────────
    # Detect a local server, create the DB, wire the DSN — or fall back to
    # offline SQLite so init always completes. The `scale` profile scaffolds the
    # DSN only (managed/external DB assumed).
    ui.section("database", db)
    try:
        from kaira.commands.db_cmd import provision_and_persist

        in_tests = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        provision_and_persist(
            db,
            name,
            project_dir,
            profile=profile,
            assume_yes=yes,
            non_interactive=in_tests or not sys.stdin.isatty(),
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
        )
    except Exception as exc:  # provisioning must never abort a successful scaffold
        ui.step("provisioning", str(exc).splitlines()[0][:60], State.FAILED)
        ui.hint("kaira db create   # once your database server is up")

    console.print()
    ui.rule()
    ok = escape(state_symbol(State.DONE))
    console.print(
        f"{GUTTER}[{Theme.SUCCESS}]{ok} {name} ready[/{Theme.SUCCESS}] "
        f"[{Theme.MUTED}]in {_elapsed_since(started)}[/{Theme.MUTED}]"
    )
    ui.hint(f"cd {name}")
    ui.hint("kaira run")


# ── Framework Upgrade Command ────────────────────────────────────────────────


def upgrade_command(
    tier: str = "standard",
    dry_run: bool = False,
    features: Optional[List[str]] = None,
) -> None:
    """Execute project tier upgrade with snapshot and rollback safety."""
    from kaira.core.theme import Theme, sym
    from kaira.migrations.engine import MigrationEngine

    engine = MigrationEngine()
    current = engine.get_current_tier()
    ui.section("upgrade", f"{current} -> {tier}")

    try:
        actions = engine.upgrade(target_tier=tier, dry_run=dry_run, features=features)
        if dry_run:
            console.print(
                f"\n[{Theme.WARNING}]DRY RUN: The following modifications would be applied:[/{Theme.WARNING}]"
            )
            for a in actions:
                console.print(f"  {sym('BULLET')} {a}")
        else:
            for a in actions:
                ui.step("upgrade", a)
            console.print(
                f"\n[{Theme.SUCCESS}]{sym('OK')} Successfully upgraded project to '{tier}' tier.[/{Theme.SUCCESS}]"
            )
    except Exception as exc:
        console.print(
            f"\n[{Theme.ERROR}]{sym('CROSS')} Upgrade failed: {exc}[/{Theme.ERROR}]"
        )
        raise typer.Exit(1)


# ── Microservice Decompose Command ───────────────────────────────────────────


def microservice_split_command(
    service_name: str,
    models: Optional[List[str]] = None,
) -> None:
    """Extract specified models and their layers into an autonomous microservice package."""
    import shutil
    from kaira.core.theme import Theme, sym

    models = models or []
    ui.section("microservice", f"Extracting {service_name}")

    service_dir = Path.cwd() / service_name
    if service_dir.exists():
        console.print(
            f"[{Theme.ERROR}]Target directory '{service_name}' already exists.[/{Theme.ERROR}]"
        )
        raise typer.Exit(1)

    service_dir.mkdir(parents=True, exist_ok=True)
    init_project(
        name=service_name,
        db="sqlite",
        auth="jwt",
        docker=True,
        ci="github",
        cwd=service_dir,
        tier="standard",
    )

    cwd = Path.cwd()
    copied = []
    for m in models:
        slug = _pascal_to_slug(m)
        for layer, sfx in [
            ("models", ""),
            ("schemas", "_schema"),
            ("services", "_service"),
            ("repositories", "_repository"),
            ("routers", "_router"),
        ]:
            src_f = cwd / layer / f"{slug}{sfx}.py"
            dst_f = service_dir / layer / f"{slug}{sfx}.py"
            if src_f.exists():
                shutil.copy2(src_f, dst_f)
                copied.append(f"{layer}/{slug}{sfx}.py")

    ui.step("scaffold", f"Created autonomous service structure in {service_name}")
    ui.step("extract", f"Extracted {len(copied)} layer file(s)")
    console.print(
        f"\n[{Theme.SUCCESS}]{sym('OK')} Microservice '{service_name}' created successfully.[/{Theme.SUCCESS}]"
    )


# ── Add Dependency Command ────────────────────────────────────────────────────


def add_dependency_command(dep: str) -> None:
    """Add a dependency package to requirements.txt and pyproject.toml."""
    from kaira.core.theme import Theme, sym

    req_path = Path.cwd() / "requirements.txt"
    if req_path.exists():
        content = req_path.read_text(encoding="utf-8")
        if dep not in content:
            req_path.write_text(content.rstrip() + f"\n{dep}\n", encoding="utf-8")
            console.print(
                f"[{Theme.SUCCESS}]{sym('OK')} Added '{dep}' to requirements.txt[/{Theme.SUCCESS}]"
            )
        else:
            console.print(
                f"[{Theme.MUTED}]'{dep}' already listed in requirements.txt[/{Theme.MUTED}]"
            )
    else:
        console.print(
            f"[{Theme.WARNING}]No requirements.txt found in current directory.[/{Theme.WARNING}]"
        )
