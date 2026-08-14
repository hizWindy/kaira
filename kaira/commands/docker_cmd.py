"""Docker scaffolding, sync, and lifecycle commands.

The generated Docker surface is a function of project state (see
:mod:`kaira.core.docker_state`), so every command here reads that state rather
than hardcoding a feature list.  Wrapping ``docker`` is only worth doing where
Kaira adds something raw Docker does not: picking the right compose and env
file, pre-flight checks, drift detection, and CI-compatible scan exit codes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 - the whole point of this module is driving docker
import time
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

from kaira.commands.smart_errors import smart_error
from kaira.commands.ux_helpers import print_next_steps, typed_confirmation
from kaira.config import get_config, set_config_values
from kaira.console import console
from kaira.core import docker_render, docker_state, ui
from kaira.core.progress import State
from kaira.core.theme import Theme, sym

app = typer.Typer(help="Docker scaffolding and execution commands.")

# Kept for backwards compatibility with callers that imported it from here.
TEMPLATES_DIR = docker_render.TEMPLATES_DIR


# ---------------------------------------------------------------------------
# Pre-flight helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run *cmd* capturing text output.  No shell, ever.

    Decoding is pinned to UTF-8 with replacement: Docker emits UTF-8 regardless
    of platform, but Python defaults to the ANSI code page on Windows, where a
    single box-drawing character in progress output would otherwise raise
    UnicodeDecodeError and take down an otherwise successful command.
    """
    return subprocess.run(  # nosec B603 - fixed argv, no shell
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def _require_docker_cli() -> None:
    """Exit with a smart error when the ``docker`` CLI is not installed."""
    if shutil.which("docker") is None:
        smart_error(
            context="The `docker` CLI was not found on PATH.",
            fix_cmd="Install Docker Desktop — https://docs.docker.com/get-docker/",
            guide_topic="docker",
        )


def _require_daemon() -> None:
    """Exit with a smart error when the Docker daemon is not reachable."""
    _require_docker_cli()
    result = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if result.returncode != 0:
        smart_error(
            context="Docker is not running.",
            fix_cmd="Start Docker Desktop or run: sudo systemctl start docker",
            guide_topic="docker",
        )


def _compose_target(prod: bool) -> tuple[Path, str]:
    """Return the ``(compose file, env file)`` pair for the requested mode."""
    if prod:
        return Path.cwd() / docker_render.COMPOSE_PROD, ".env.production"
    return Path.cwd() / docker_render.COMPOSE_DEV, ".env.development"


def _require_compose_file(prod: bool) -> tuple[Path, str]:
    """Resolve and validate the compose file for the requested mode."""
    compose_path, env_file = _compose_target(prod)
    if not compose_path.is_file():
        smart_error(
            context=f"No {compose_path.name} in this project.",
            fix_cmd="kaira docker init --with-compose",
            guide_topic="docker",
        )
    return compose_path, env_file


def _compose_cmd(compose_path: Path, env_file: str) -> list[str]:
    """Build the ``docker compose`` prefix, including --env-file when present.

    Compose errors out on a missing ``--env-file``, so the flag is only added
    when the file actually exists — a project that keeps its configuration in
    the shell environment still works.
    """
    cmd = ["docker", "compose", "-f", str(compose_path)]
    if (Path.cwd() / env_file).is_file():
        cmd += ["--env-file", env_file]
    return cmd


def _warn_if_out_of_sync() -> None:
    """Warn — and offer to fix — when Docker files no longer match project state."""
    if not docker_render.is_out_of_sync():
        return
    ui.step("sync", "Docker files do not match project state", State.PARTIAL)
    ui.hint("kaira docker sync")


def _image_size(tag: str) -> str:
    """Return a human-readable size for *tag*, or ``"—"`` when unknown.

    Read from ``docker image ls`` rather than ``docker image inspect``: under
    the containerd image store ``inspect``'s ``.Size`` reports the compressed
    content size, which is roughly a quarter of the on-disk size the user sees
    everywhere else.
    """
    result = _run(["docker", "image", "ls", "--format", "{{.Size}}", tag])
    if result.returncode != 0:
        return "—"
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[0] if lines else "—"


def _supports_init_flag() -> bool:
    """True when the installed Docker is new enough for ``docker run --init``.

    ``--init`` landed in Docker 17.06; anything older falls back with a warning
    rather than failing the run outright.
    """
    result = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    if result.returncode != 0:
        return False
    parts = result.stdout.strip().split(".")
    try:
        return (int(parts[0]), int(parts[1])) >= (17, 6)
    except (ValueError, IndexError):
        return False


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@app.command("init")
def docker_init(
    with_compose: Annotated[
        bool, typer.Option("--with-compose", help="Also scaffold docker-compose files.")
    ] = False,
    python: Annotated[
        Optional[str],
        typer.Option(
            "--python",
            help="Python version for the Dockerfile base image (3.10–3.13).",
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Non-interactive: never prompt.")
    ] = False,
) -> None:
    """Scaffold Dockerfile, .dockerignore, and compose files from project state."""
    start = time.perf_counter()

    try:
        resolved_python = docker_state.resolve_python_version(python)
    except docker_state.InvalidPythonVersion:
        smart_error(
            context="Unsupported Python version for the Docker base image.",
            typed=python or "",
            candidates=docker_state.SUPPORTED_PYTHON,
            fix_cmd="kaira docker init --python 3.12",
            guide_topic="docker",
        )
        return  # pragma: no cover - smart_error always exits

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    state = docker_state.resolve_state(output_root, python_version=resolved_python)

    ui.section("docker init", state.project_name)
    ui.field("python", f"{resolved_python}-slim")
    ui.field("database", docker_state.db_label(state.db_type))
    ui.field("services", ", ".join(docker_state.enabled_features(state)))

    plans = docker_render.build_plan(
        output_root, state=state, with_compose=with_compose
    )
    written, skipped = docker_render.apply_plan(plans, force=force, quiet=quiet)

    for plan in plans:
        if plan.status == "same":
            ui.step(plan.path.name, "already up to date", State.DONE)
        elif plan.needs_write:
            ui.step(plan.path.name, plan.status, State.DONE)

    set_config_values(
        docker_enabled=True,
        docker_compose=with_compose or config.docker_compose,
        docker_python=resolved_python,
    )

    steps = ["Build the image:  [bold cyan]kaira docker build[/bold cyan]"]
    if with_compose:
        steps.append("Start the stack:  [bold cyan]kaira docker up[/bold cyan]")
    else:
        steps.append("Run the container:  [bold cyan]kaira docker run[/bold cyan]")
    steps.append("Scan for CVEs:  [bold cyan]kaira docker scan[/bold cyan]")
    steps.append(
        "Re-sync after project changes:  [bold cyan]kaira docker sync[/bold cyan]"
    )
    print_next_steps(steps, quiet=quiet)

    ui.success_footer(
        "Docker scaffold ready",
        elapsed_s=time.perf_counter() - start,
        files=written,
        warnings=skipped,
    )


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


@app.command("sync")
def docker_sync(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the diff without writing.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite without prompting.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", help="Non-interactive: overwrite silently.")
    ] = False,
) -> None:
    """Regenerate Docker files so they match the current project state."""
    start = time.perf_counter()

    config = get_config()
    output_root = Path.cwd() / config.output_dir

    if not docker_render.docker_enabled(output_root):
        smart_error(
            context="This project has no generated Dockerfile to sync.",
            fix_cmd="kaira docker init --with-compose",
            guide_topic="docker",
        )

    state = docker_state.resolve_state(output_root)
    ui.section("docker sync", state.project_name)
    ui.field("database", docker_state.db_label(state.db_type))
    ui.field("services", ", ".join(docker_state.enabled_features(state)))

    plans = docker_render.build_plan(output_root, state=state)
    pending = [plan for plan in plans if plan.needs_write]

    if not pending:
        ok = sym("OK")
        console.print(
            f"  [{Theme.SUCCESS}]{ok} Docker files are up to date.[/{Theme.SUCCESS}]"
        )
        ui.success_footer(
            "Already in sync", elapsed_s=time.perf_counter() - start, files=0
        )
        return

    for plan in pending:
        ui.step(plan.path.name, plan.status, State.PARTIAL)

    if dry_run:
        for plan in pending:
            docker_render.show_diff(plan)
        ui.hint("kaira docker sync")
        ui.success_footer(
            "Dry run — nothing written",
            elapsed_s=time.perf_counter() - start,
            files=0,
            warnings=len(pending),
        )
        return

    if any(plan.status == "changed" for plan in pending) and not (force or quiet):
        console.print(
            f"  [{Theme.WARNING}]Manual edits to these files will be lost "
            f"on overwrite.[/{Theme.WARNING}]"
        )

    written, skipped = docker_render.apply_plan(pending, force=force, quiet=quiet)
    ui.success_footer(
        "Docker files synced",
        elapsed_s=time.perf_counter() - start,
        files=written,
        warnings=skipped,
    )


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

_BUILD_HINTS: list[tuple[str, str, str]] = [
    (
        "requirements.txt: no such file",
        "The build context has no requirements.txt.",
        "kaira deps freeze",
    ),
    (
        "failed to compute cache key",
        "A file the Dockerfile COPYs is missing from the build context.",
        "Check .dockerignore — it may be excluding a file the Dockerfile needs.",
    ),
    (
        "dockerfile parse error",
        "The Dockerfile has a syntax error.",
        "kaira docker sync",
    ),
    (
        "temporary failure in name resolution",
        "The build could not reach the network during pip install.",
        "Check your connection or proxy, then re-run: kaira docker build",
    ),
    (
        "read timed out",
        "pip timed out downloading a dependency.",
        "Re-run: kaira docker build",
    ),
    (
        "no space left on device",
        "The Docker host is out of disk space.",
        "docker system prune -a",
    ),
]


_BUILD_NOISE_RE = re.compile(
    r"view build details:|docker-desktop://|^#\d+ ", re.IGNORECASE
)
"""Lines that are never the actual error.

The Docker Desktop `desktop-linux` builder ends failed output with a link to
open the GUI dashboard rather than the error itself, and BuildKit prefixes
every progress line with a `#<step>` marker — both would otherwise look like
"the last line" and get surfaced as if they explained the failure.
"""


def _build_failure_hint(output: str) -> tuple[str, str]:
    """Map raw Docker build output to ``(explanation, fix)``."""
    lowered = output.lower()
    for needle, context, fix in _BUILD_HINTS:
        if needle in lowered:
            return context, fix

    lines = [
        line.strip()
        for line in output.strip().splitlines()
        if line.strip() and not _BUILD_NOISE_RE.search(line)
    ]
    # BuildKit reports the real cause on an "ERROR:" line, usually followed by
    # noise (the dashboard link) or blank lines — so the last ERROR line beats
    # whatever line happens to be last.
    error_lines = [line for line in lines if "error" in line.lower()]
    detail = (error_lines or lines or ["Docker build failed."])[-1]
    return detail[:200], "kaira docker build --verbose"


@app.command("build")
def docker_build(
    tag: Annotated[
        str, typer.Option("-t", "--tag", help="Build tag name.")
    ] = "kaira-app",
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Stream full Docker build output.")
    ] = False,
) -> None:
    """Build the application image."""
    start = time.perf_counter()
    _require_daemon()

    if not (Path.cwd() / docker_render.DOCKERFILE).is_file():
        smart_error(
            context="No Dockerfile in this project.",
            fix_cmd="kaira docker init",
            guide_topic="docker",
        )

    ui.section("docker build", tag)
    _warn_if_out_of_sync()

    cmd = ["docker", "build", "-t", tag, "."]

    if verbose:
        result = subprocess.run(cmd, check=False)  # nosec B603 - fixed argv, no shell
        output = ""
        returncode = result.returncode
    else:
        with ui.spinner_context(f"building {tag}"):
            completed = _run(cmd)
        output = completed.stdout + completed.stderr
        returncode = completed.returncode

    elapsed = time.perf_counter() - start

    if returncode != 0:
        context, fix = _build_failure_hint(output)
        ui.step("build", "failed", State.FAILED)
        smart_error(
            context=f"Docker build failed. {context}",
            fix_cmd=fix,
            guide_topic="docker",
        )

    ui.step("image", tag, State.DONE)
    ui.field("size", _image_size(tag))
    ui.success_footer("Image built", elapsed_s=elapsed, files=None)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command("run")
def docker_run(
    tag: Annotated[
        str, typer.Option("-t", "--tag", help="Tag name of the image to run.")
    ] = "kaira-app",
    port: Annotated[
        int, typer.Option("-p", "--port", help="Host port mapping.")
    ] = 8000,
    env_file: Annotated[
        str, typer.Option("--env-file", help="Env file passed to the container.")
    ] = ".env",
    init: Annotated[
        bool,
        typer.Option(
            "--init/--no-init",
            help="Run an init process as PID 1 (signal forwarding, zombie reaping).",
        ),
    ] = True,
) -> None:
    """Run the image with Kaira's hardened defaults."""
    start = time.perf_counter()
    _require_daemon()

    ui.section("docker run", tag)

    cmd = ["docker", "run", "-d", "-p", f"{port}:8000"]

    if init:
        if _supports_init_flag():
            cmd.append("--init")
        else:
            ui.note("init", "Docker < 17.06 — --init not available, continuing without")

    # A `docker run --tmpfs` mount spec, not a path this process writes to
    # directly; size-capped and wiped when the container stops.
    cmd += ["--read-only", "--tmpfs", "/tmp:size=64m"]  # nosec B108
    cmd += ["--security-opt", "no-new-privileges:true"]

    if (Path.cwd() / env_file).is_file():
        cmd += ["--env-file", env_file]
    else:
        ui.note("env", f"{env_file} not found — starting with the ambient environment")

    cmd.append(tag)

    result = _run(cmd)
    if result.returncode != 0:
        ui.step("container", "failed to start", State.FAILED)
        smart_error(
            context=(result.stderr.strip().splitlines() or ["docker run failed."])[-1][
                :200
            ],
            fix_cmd=f"kaira docker build --tag {tag}",
            guide_topic="docker",
        )

    container_id = result.stdout.strip()[:12]
    ui.step("container", container_id, State.DONE)
    ui.field("url", f"http://localhost:{port}")
    ui.success_footer("Container running", elapsed_s=time.perf_counter() - start)


# ---------------------------------------------------------------------------
# up
# ---------------------------------------------------------------------------


def _typed_confirm(name: str, action: str) -> bool:
    """Require the user to type *name* to confirm *action*.

    Unlike :func:`~kaira.commands.ux_helpers.typed_confirmation` this does not
    refuse to run under ``APP_ENV=production`` — starting the production stack
    in production is the intended use, it just deserves a deliberate keystroke.
    """
    warn = sym("WARN")
    console.print(
        f"  [{Theme.WARNING}]{warn}  {action}[/{Theme.WARNING}]\n"
        f"  Type [bold]{name}[/bold] to confirm, or press Enter to abort:"
    )
    answer = typer.prompt("", default="")
    if answer.strip() != name:
        console.print(f"  [{Theme.MUTED}]Aborted.[/{Theme.MUTED}]")
        return False
    return True


def _compose_services_status(compose_path: Path, env_file: str) -> list[dict[str, Any]]:
    """Return ``docker compose ps`` rows as structured data.

    Uses ``--format json`` rather than parsing the human table.  Compose emits
    a JSON array on some versions and newline-delimited objects on others, so
    both shapes are accepted.
    """
    result = _run(_compose_cmd(compose_path, env_file) + ["ps", "--format", "json"])
    if result.returncode != 0:
        return []

    raw = result.stdout.strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
        return list(parsed) if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        pass

    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _format_ports(row: dict[str, Any]) -> str:
    """Return published ports for a compose ps row."""
    publishers = row.get("Publishers") or []
    mapped = {
        f"{pub.get('PublishedPort')}→{pub.get('TargetPort')}"
        for pub in publishers
        if isinstance(pub, dict) and pub.get("PublishedPort")
    }
    return ", ".join(sorted(mapped)) if mapped else "—"


@app.command("up")
def docker_up(
    prod: Annotated[
        bool, typer.Option("--prod", help="Target the production compose file.")
    ] = False,
    build: Annotated[
        bool, typer.Option("--build", help="Rebuild images before starting.")
    ] = False,
    detach: Annotated[
        Optional[bool],
        typer.Option("--detach/--no-detach", help="Run in the background."),
    ] = None,
) -> None:
    """Start the stack with the right compose file, env file, and defaults."""
    start = time.perf_counter()

    _require_daemon()
    compose_path, env_file = _require_compose_file(prod)

    ui.section("docker up", "production" if prod else "development")
    ui.field("compose", compose_path.name)
    ui.field("env", env_file)
    _warn_if_out_of_sync()

    if prod:
        project_name = Path.cwd().name
        if not _typed_confirm(
            project_name,
            f"Starting the PRODUCTION stack from {compose_path.name}.",
        ):
            raise typer.Exit(1)

    # Production defaults to detached: a foreground production stack dies with
    # the terminal that started it.
    detached = prod if detach is None else detach

    cmd = _compose_cmd(compose_path, env_file) + ["up"]
    if build:
        cmd.append("--build")
    if detached:
        cmd.append("-d")

    if not detached:
        console.print(
            f"  [{Theme.MUTED}]Streaming logs — Ctrl+C stops the stack.[/{Theme.MUTED}]"
        )
        try:
            result = subprocess.run(cmd, check=False)  # nosec B603 - fixed argv
        except KeyboardInterrupt:
            console.print(f"\n  [{Theme.MUTED}]Stopped.[/{Theme.MUTED}]")
            raise typer.Exit(0)
        if result.returncode != 0:
            ui.step("stack", "exited with an error", State.FAILED)
            raise typer.Exit(result.returncode)
        ui.success_footer("Stack stopped", elapsed_s=time.perf_counter() - start)
        return

    with ui.spinner_context("starting services"):
        completed = _run(cmd)

    if completed.returncode != 0:
        ui.step("stack", "failed to start", State.FAILED)
        smart_error(
            context=(completed.stderr.strip().splitlines() or ["compose up failed."])[
                -1
            ][:200],
            fix_cmd="kaira docker sync",
            guide_topic="docker",
        )

    for row in _compose_services_status(compose_path, env_file):
        service = str(row.get("Service") or row.get("Name") or "?")
        health = str(row.get("Health") or "").strip()
        status = str(row.get("State") or "").strip()
        detail = f"{status} · {health}" if health else status
        state = State.DONE if status == "running" else State.PARTIAL
        ui.step(service, detail, state)

    ui.field("url", "http://localhost:8000")
    ui.success_footer("Stack running", elapsed_s=time.perf_counter() - start)


# ---------------------------------------------------------------------------
# down
# ---------------------------------------------------------------------------


@app.command("down")
def docker_down(
    prod: Annotated[
        bool, typer.Option("--prod", help="Target the production compose file.")
    ] = False,
    volumes: Annotated[
        bool, typer.Option("--volumes", help="Also destroy data volumes.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Skip the typed confirmation.")
    ] = False,
) -> None:
    """Stop the stack, optionally destroying its data volumes."""
    start = time.perf_counter()

    _require_daemon()
    compose_path, env_file = _require_compose_file(prod)

    ui.section("docker down", "production" if prod else "development")
    ui.field("compose", compose_path.name)

    if volumes:
        # typed_confirmation refuses outright under APP_ENV=production — data
        # destruction is never a production operation.
        if not typed_confirmation(
            Path.cwd().name,
            "This destroys every data volume in the stack — databases included.",
            force=force,
        ):
            raise typer.Exit(1)

    cmd = _compose_cmd(compose_path, env_file) + ["down"]
    if volumes:
        cmd.append("--volumes")

    with ui.spinner_context("stopping services"):
        completed = _run(cmd)

    if completed.returncode != 0:
        ui.step("stack", "failed to stop", State.FAILED)
        smart_error(
            context=(completed.stderr.strip().splitlines() or ["compose down failed."])[
                -1
            ][:200],
            fix_cmd="docker compose ls",
            guide_topic="docker",
        )

    ui.step("containers", "stopped", State.DONE)
    ui.step("network", "removed", State.DONE)
    if volumes:
        ui.step("volumes", "destroyed", State.DONE)

    ui.success_footer("Stack down", elapsed_s=time.perf_counter() - start)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def _volume_sizes() -> dict[str, str]:
    """Return ``volume name → size`` from ``docker system df``.

    Best effort: the output shape varies between Docker versions, so a failure
    here degrades to "size unknown" rather than breaking the command.
    """
    result = _run(["docker", "system", "df", "-v", "--format", "{{json .Volumes}}"])
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        rows = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {}
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("Name")): str(row.get("Size", "—"))
        for row in rows
        if isinstance(row, dict) and row.get("Name")
    }


@app.command("status")
def docker_status(
    prod: Annotated[
        bool, typer.Option("--prod", help="Target the production compose file.")
    ] = False,
) -> None:
    """Show this project's containers, their health, and image/volume facts.

    Container metadata only — connection strings and env values are never read
    or printed.
    """
    start = time.perf_counter()

    _require_daemon()
    compose_path, env_file = _require_compose_file(prod)

    state = docker_state.resolve_state(Path.cwd() / get_config().output_dir)

    ui.section("docker status", state.project_name)

    rows = _compose_services_status(compose_path, env_file)
    if not rows:
        ui.note("containers", "none running")
        ui.hint("kaira docker up")
        ui.success_footer(
            "No containers running", elapsed_s=time.perf_counter() - start
        )
        return

    table_rows: list[list[str]] = []
    for row in rows:
        table_rows.append(
            [
                str(row.get("Service") or row.get("Name") or "?"),
                str(row.get("State") or "—"),
                _format_ports(row),
                str(row.get("RunningFor") or row.get("Status") or "—"),
                str(row.get("Health") or "—") or "—",
            ]
        )

    ui.data_table(
        ["Service", "State", "Ports", "Uptime", "Health"],
        table_rows,
    )

    image = str(rows[0].get("Image") or "") if rows else ""
    if image:
        ui.field("image", f"{image} · {_image_size(image)}")
    ui.field("database", docker_state.db_label(state.db_type))
    ui.field("environment", "production" if prod else "development")

    sizes = _volume_sizes()
    services = docker_state.build_services(
        state, docker_state.PROD if prod else docker_state.DEV
    )
    for name in docker_state.collect_volume_names(services):
        # Compose prefixes named volumes with the project directory name.
        qualified = f"{state.project_slug}_{name}"
        ui.field(
            f"volume {name}", sizes.get(qualified) or sizes.get(name) or "size unknown"
        )

    ui.success_footer("Status", elapsed_s=time.perf_counter() - start)


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
_SEVERITY_STYLE = {
    "CRITICAL": Theme.ERROR,
    "HIGH": Theme.ERROR,
    "MEDIUM": Theme.WARNING,
    "LOW": Theme.MUTED,
    "UNKNOWN": Theme.MUTED,
}
_FAILING_SEVERITIES = {"CRITICAL", "HIGH"}


def _resolve_scanner() -> Optional[str]:
    """Return the first available scanner: docker scout, trivy, then grype."""
    if shutil.which("docker") and _run(["docker", "scout", "version"]).returncode == 0:
        return "scout"
    if shutil.which("trivy"):
        return "trivy"
    if shutil.which("grype"):
        return "grype"
    return None


def _parse_trivy(payload: str) -> list[dict[str, str]]:
    """Parse ``trivy image --format json`` output."""
    findings: list[dict[str, str]] = []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return findings
    for result in data.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            findings.append(
                {
                    "id": str(vuln.get("VulnerabilityID", "—")),
                    "package": str(vuln.get("PkgName", "—")),
                    "installed": str(vuln.get("InstalledVersion", "—")),
                    "severity": str(vuln.get("Severity", "UNKNOWN")).upper(),
                    "fixed": str(vuln.get("FixedVersion") or "—"),
                }
            )
    return findings


def _parse_grype(payload: str) -> list[dict[str, str]]:
    """Parse ``grype -o json`` output."""
    findings: list[dict[str, str]] = []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return findings
    for match in data.get("matches") or []:
        vuln = match.get("vulnerability") or {}
        artifact = match.get("artifact") or {}
        fix_versions = (vuln.get("fix") or {}).get("versions") or []
        findings.append(
            {
                "id": str(vuln.get("id", "—")),
                "package": str(artifact.get("name", "—")),
                "installed": str(artifact.get("version", "—")),
                "severity": str(vuln.get("severity", "UNKNOWN")).upper(),
                "fixed": ", ".join(fix_versions) if fix_versions else "—",
            }
        )
    return findings


def _split_purl(purl: str) -> tuple[str, str]:
    """Split a package URL into ``(name, version)``.

    ``pkg:deb/debian/shadow@1%3A4.13+dfsg1-1?arch=amd64`` → ``("shadow", "1:4.13+dfsg1-1")``.
    Percent-encoding is undone so an epoch reads as ``1:`` rather than ``1%3A``.
    """
    from urllib.parse import unquote

    tail = purl.split("?", 1)[0].rsplit("/", 1)[-1]
    name, _, version = tail.partition("@")
    return unquote(name) or "—", unquote(version) or "—"


def _parse_scout_sarif(payload: str) -> list[dict[str, str]]:
    """Parse ``docker scout cves --format sarif`` output.

    Scout's SARIF carries severity and version facts in per-rule ``properties``;
    the keys have shifted between releases, so several spellings are accepted
    and anything unrecognised degrades to ``UNKNOWN`` rather than being dropped.
    """
    findings: list[dict[str, str]] = []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return findings

    for run in data.get("runs") or []:
        rules = {
            str(rule.get("id")): rule
            for rule in ((run.get("tool") or {}).get("driver") or {}).get("rules") or []
        }
        for result in run.get("results") or []:
            rule = rules.get(str(result.get("ruleId")), {})
            props = rule.get("properties") or {}
            severity = str(
                props.get("cvssV3_severity")
                or props.get("security-severity")
                or props.get("severity")
                or "UNKNOWN"
            ).upper()
            purls = props.get("purls") or []
            if purls:
                package, installed = _split_purl(str(purls[0]))
            else:
                package = str(props.get("name", "—"))
                installed = str(props.get("affected_version", "—"))

            findings.append(
                {
                    "id": str(result.get("ruleId") or rule.get("id") or "—"),
                    "package": package,
                    "installed": installed,
                    "severity": severity if severity in _SEVERITY_ORDER else "UNKNOWN",
                    "fixed": str(props.get("fixed_version") or "—"),
                }
            )
    return findings


def _scan_command(scanner: str, tag: str) -> list[str]:
    """Return the argv that makes *scanner* emit machine-readable output."""
    if scanner == "trivy":
        return ["trivy", "image", "--quiet", "--format", "json", tag]
    if scanner == "grype":
        return ["grype", tag, "-o", "json", "-q"]
    return ["docker", "scout", "cves", "--format", "sarif", tag]


@app.command("scan")
def docker_scan(
    tag: Annotated[
        str, typer.Option("-t", "--tag", help="Image tag to scan.")
    ] = "kaira-app",
    fix: Annotated[
        bool, typer.Option("--fix", help="Include the fixed-in version column.")
    ] = False,
    remote: Annotated[
        bool,
        typer.Option("--remote", help="Allow pulling the image from a registry."),
    ] = False,
) -> None:
    """Scan the project image for known CVEs.

    Exits 1 when any HIGH or CRITICAL vulnerability is present, so the command
    can gate a CI pipeline directly.
    """
    start = time.perf_counter()
    _require_daemon()

    scanner = _resolve_scanner()
    if scanner is None:
        smart_error(
            context="No image scanner found. Install one of docker scout, trivy, or grype.",
            fix_cmd=(
                "docker scout (bundled with Docker Desktop) · "
                "brew install trivy · brew install grype"
            ),
            guide_topic="docker",
        )
        return  # pragma: no cover - smart_error always exits

    ui.section("docker scan", tag)
    ui.field("scanner", str(scanner))

    if not remote:
        # Local-only by default: a typo in --tag should not pull a stranger's
        # multi-gigabyte image onto the machine.
        exists = _run(["docker", "image", "inspect", tag])
        if exists.returncode != 0:
            smart_error(
                context=f"Image '{tag}' is not present locally.",
                fix_cmd=f"kaira docker build --tag {tag}   (or pass --remote)",
                guide_topic="docker",
            )

    with ui.spinner_context(f"scanning {tag}"):
        completed = _run(_scan_command(scanner, tag))

    parsers = {
        "trivy": _parse_trivy,
        "grype": _parse_grype,
        "scout": _parse_scout_sarif,
    }
    findings = parsers[scanner](completed.stdout)

    if not findings and completed.returncode != 0:
        ui.step("scan", "scanner failed", State.FAILED)
        smart_error(
            context=(completed.stderr.strip().splitlines() or ["Scanner failed."])[-1][
                :200
            ],
            fix_cmd=f"{scanner} --help",
            guide_topic="docker",
        )

    if not findings:
        ok = sym("OK")
        console.print(
            f"  [{Theme.SUCCESS}]{ok} No known vulnerabilities found.[/{Theme.SUCCESS}]"
        )
        ui.success_footer("Scan clean", elapsed_s=time.perf_counter() - start)
        return

    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 4), f["package"]))

    headers = ["Package", "Severity", "Installed", "CVE"]
    if fix:
        headers.append("Fixed in")

    rows: list[list[str]] = []
    for finding in findings:
        style = _SEVERITY_STYLE.get(finding["severity"], Theme.MUTED)
        row = [
            finding["package"],
            f"[{style}]{finding['severity']}[/{style}]",
            finding["installed"],
            finding["id"],
        ]
        if fix:
            row.append(finding["fixed"])
        rows.append(row)

    ui.data_table(headers, rows)

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    summary = " · ".join(
        f"{sev.lower()}: {counts[sev]}"
        for sev in sorted(counts, key=lambda s: _SEVERITY_ORDER.get(s, 4))
    )
    ui.field("total", summary)

    blocking = sum(counts.get(sev, 0) for sev in _FAILING_SEVERITIES)
    elapsed = time.perf_counter() - start

    if blocking:
        ui.error_footer(
            f"{blocking} high/critical vulnerabilit{'y' if blocking == 1 else 'ies'}",
            hint="rebuild on a newer base image, then re-scan",
        )
        raise typer.Exit(1)

    ui.success_footer(
        "Scan complete — no high or critical findings",
        elapsed_s=elapsed,
        warnings=len(findings),
    )
