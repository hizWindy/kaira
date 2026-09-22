"""Kaira monitor command group — runtime application monitoring.

Four commands, one rule: **nothing here touches a project unless the user runs
it.** ``kaira monitor init`` is opt-in in exactly the way ``cache init`` and
``task init`` are, it never silently overwrites ``main.py``, and a project that
never runs it is byte-for-byte what it was before this phase existed.

    kaira monitor init      scaffold metrics, probes, and (opt-in) the dashboard
    kaira monitor status    what is configured, and what is actually running
    kaira monitor watch     tail live metrics, alert when a threshold trips
    kaira monitor diff      compare two saved metrics snapshots

What ``init`` will not do
-------------------------
* It does not modify ``/health``. Phase 4 owns that route; ``/healthz`` and
  ``/readyz`` are added beside it, and Docker's ``HEALTHCHECK`` keeps pointing
  where it always did.
* It does not reorder middleware. The metrics middleware is spliced in *after*
  ``register_security_middleware(app)`` — security stays first, and the metrics
  middleware reads the duration that middleware already computed instead of
  timing the request a second time.
* It does not write log files. ``KAIRA_LOG_FORMAT=json`` switches the existing
  stdout formatter; there is no file sink, here or anywhere else in Kaira.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess  # nosec B404 - used only to hand a desktop notifier a string
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.markup import escape

from kaira.commands.ux_helpers import append_history, print_next_steps, require_project
from kaira.console import console
from kaira.core import monitor_state
from kaira.core.docker_render import FilePlan, apply_plan, show_diff
from kaira.core.monitor_state import (
    AUTH_REUSE,
    AUTH_STRATEGIES,
    AUTH_TOKEN,
    DASHBOARD_DATA_ROUTE,
    ENV_MONITOR_ENABLED,
    ENV_MONITOR_TOKEN,
    ENV_MONITOR_WEBHOOK,
    LIVENESS_ROUTE,
    METRICS_ROUTE,
    MONITOR_NAMESPACE,
    READINESS_ROUTE,
    MonitorState,
    mask_webhook_url,
)
from kaira.core.progress import State
from kaira.core.theme import Theme, is_interactive, sym
from kaira.core.ui import field, hint, kv_table, note, panel, section, step, subtext

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Runtime application monitoring — metrics, probes, dashboard.")

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
"""Address assumed when no server is running to be found."""


def _default_base_url() -> str:
    """Return the address of the running application.

    ``kaira run`` moves off a taken port and records where it landed, so the
    address is resolved when the command runs rather than fixed at import: a
    constant would point at :8000 while the app answers on :8001.
    """
    from kaira.core.ports import resolve_base_url

    return resolve_base_url()


# main.py splice anchors. All three are written by the Phase 3/4 templates, so a
# project that has them is one Kaira generated; a project that does not gets a
# printed instruction instead of a guessed edit.
_SECURITY_IMPORT = "from middleware.security import"
_SECURITY_CALL = "register_exception_handlers(app)"

_METRICS_IMPORT = "from middleware.metrics import register_metrics_middleware"
_METRICS_CALL = "register_metrics_middleware(app)"
_METRICS_BLOCK = (
    "\n# Metrics middleware — registered AFTER the security middleware, never\n"
    "# before it: that ordering is what lets it read the duration already\n"
    "# computed for X-Response-Time instead of timing the request twice.\n"
    f"{_METRICS_CALL}\n"
)

_PROBES_IMPORT = "from routers.probes_router import router as probes_router"
_PROBES_INCLUDE = "app.include_router(probes_router)"
_MONITOR_IMPORT = "from routers.monitor_router import router as monitor_router"
_MONITOR_INCLUDE = "app.include_router(monitor_router)"

_PROMETHEUS_REQUIREMENT = "prometheus-client>=0.20.0"

_ALERT_ERROR_RATE = 0.05
_ALERT_P95_MS = 1000.0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _jinja() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701 - generating Python modules, not HTML
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_monitor_files(state: MonitorState, *, dashboard: bool) -> dict[str, str]:
    """Render every monitoring module for *state*.

    Args:
        state: Resolved monitoring state, carrying the chosen auth strategy.
        dashboard: Whether the Tier 2 dashboard files are part of this surface.

    Returns:
        Mapping of project-relative path → rendered module source.
    """
    env = _jinja()
    context = monitor_state.build_context(state)

    features = list(monitor_state.TIER1_FEATURES)
    if dashboard:
        features += list(monitor_state.TIER2_FEATURES)

    rendered: dict[str, str] = {}
    for key in features:
        path, template = monitor_state.GENERATED_FILES[key]
        rendered[path] = env.get_template(template).render(**context)
    return rendered


def render_sdk_module(provider: str, project_name: str) -> str:
    """Render ``core/monitor_sdk.py`` for a third-party provider.

    Args:
        provider: ``sentry``, ``datadog`` or ``newrelic``.
        project_name: Name used in the module docstring.

    Returns:
        The rendered module source.
    """
    return (
        _jinja()
        .get_template(monitor_state.SDK_TEMPLATE)
        .render(
            provider=provider,
            provider_label={"newrelic": "New Relic"}.get(provider, provider.title()),
            project_name=project_name,
            dev_rate=monitor_state.sampling_default(provider, "development"),
            prod_rate=monitor_state.sampling_default(provider, "production"),
        )
    )


# ---------------------------------------------------------------------------
# main.py wiring
# ---------------------------------------------------------------------------


def splice_main(content: str, *, dashboard: bool) -> str:
    """No-op: KairaApp auto-discovers monitoring routes via providers.

    Since ``kaira init`` generates projects with ``KairaApp``, monitoring
    is registered via ``app.register_provider(MonitorProvider())`` at runtime.
    This function returns content unchanged for backward compatibility.
    """
    return content


def _plan_for(path: Path, content: str) -> FilePlan:
    """Build a :class:`FilePlan` comparing *path* on disk against *content*."""
    if not path.is_file():
        status = "new"
    else:
        try:
            status = (
                "same" if path.read_text(encoding="utf-8") == content else "changed"
            )
        except OSError:
            status = "changed"
    return FilePlan(path=path, content=content, status=status)


def build_init_plan(
    root: Path, state: MonitorState, *, dashboard: bool
) -> list[FilePlan]:
    """Return every file ``monitor init`` would write, with its drift status.

    Args:
        root: Project output root.
        state: Resolved monitoring state.
        dashboard: Whether Tier 2 files are included.

    Returns:
        Plans in write order: modules first, then the ``main.py`` edit, then the
        logger regeneration if JSON log mode is not already available.
    """
    plans = [
        _plan_for(root / name, content)
        for name, content in render_monitor_files(state, dashboard=dashboard).items()
    ]

    main_path = root / "main.py"
    if main_path.is_file():
        try:
            current = main_path.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current:
            plans.append(
                _plan_for(main_path, splice_main(current, dashboard=dashboard))
            )

    logger_path = root / "core" / "logger.py"
    if logger_path.is_file() and not monitor_state.detect_json_logs(root):
        rendered = (
            _jinja()
            .get_template("logger.py.j2")
            .render(project_name=state.project_name)
        )
        plans.append(_plan_for(logger_path, rendered))

    return plans


# ---------------------------------------------------------------------------
# Env / settings / requirements
# ---------------------------------------------------------------------------


def _update_env_files(key: str, value: str) -> None:
    """Add *key* to every ``.env*`` file that does not already declare it."""
    for env_file in Path.cwd().glob(".env*"):
        if env_file.is_dir():
            continue
        try:
            content = env_file.read_text(encoding="utf-8")
            if f"{key}=" not in content:
                env_file.write_text(f"{content}\n{key}={value}\n", encoding="utf-8")
        except OSError:
            pass


def _settings_path(root: Path) -> Optional[Path]:
    """Return the project's settings module, or ``None`` when absent."""
    for candidate in (root / "config" / "settings.py", root / "core" / "config.py"):
        if candidate.is_file():
            return candidate
    return None


def _add_settings_field(root: Path, line: str, marker: str) -> bool:
    """Append a settings field when *marker* is not already declared."""
    path = _settings_path(root)
    if path is None:
        return False
    try:
        content = path.read_text(encoding="utf-8")
        if marker in content:
            return False
        path.write_text(content.rstrip() + f"\n{line}\n", encoding="utf-8")
    except OSError:
        return False
    return True


def _ensure_requirement(root: Path) -> bool:
    """Add ``prometheus-client`` to ``requirements.txt`` when it is missing."""
    path = root / "requirements.txt"
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8")
        if "prometheus-client" in content:
            return False
        path.write_text(
            content.rstrip()
            + f"\n\n# Monitoring (kaira monitor init)\n{_PROMETHEUS_REQUIREMENT}\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def _read_env_value(key: str) -> str:
    """Return *key* from the environment, falling back to the project's .env files."""
    value = os.getenv(key, "").strip()
    if value:
        return value
    for name in (".env", ".env.development", ".env.local"):
        path = Path.cwd() / name
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip("'\"")
        except OSError:
            continue
    return ""


def _generate_token() -> str:
    """Return a fresh dashboard bearer token."""
    import secrets

    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# kaira monitor init
# ---------------------------------------------------------------------------


@app.command("init")
def monitor_init(
    dashboard: Annotated[
        bool,
        typer.Option(
            "--dashboard",
            help=f"Also scaffold the self-hosted mini dashboard at {MONITOR_NAMESPACE}.",
        ),
    ] = False,
    auth: Annotated[
        Optional[str],
        typer.Option(
            "--auth",
            help="Dashboard auth strategy: reuse | token. Required with --dashboard "
            "when not running interactively.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite changed files without prompting."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", help="Non-interactive: never prompt (CI-friendly)."),
    ] = False,
) -> None:
    """Scaffold the monitoring surface for this project.

    Writes ``core/metrics.py``, ``middleware/metrics.py`` and
    ``routers/probes_router.py``, then wires them into ``main.py`` through the
    standard diff/confirm prompt. ``/health`` is not touched and the security
    middleware keeps its position.

    Examples
    --------
    kaira monitor init
    kaira monitor init --dashboard --auth token
    kaira monitor init --dashboard --auth reuse --quiet
    """
    require_project()

    from kaira.config import get_config, set_config_values

    cfg = get_config()
    root = Path.cwd() / cfg.output_dir
    state = monitor_state.resolve_state(Path.cwd())

    strategy = _resolve_auth_strategy(
        state, dashboard=dashboard, auth=auth, quiet=quiet
    )
    if dashboard:
        state = replace_auth(state, strategy)

    section(
        "plan", f"{state.project_name} · tier 1{' + dashboard' if dashboard else ''}"
    )
    plans = build_init_plan(root, state, dashboard=dashboard)
    pending = [plan for plan in plans if plan.needs_write]

    for plan in plans:
        label = (
            plan.path.relative_to(root).as_posix()
            if plan.path.is_relative_to(root)
            else plan.path.name
        )
        if plan.status == "new":
            step(label, "new file", State.PENDING)
        elif plan.status == "changed":
            step(label, "will be rewritten — diff shown before writing", State.PARTIAL)
        else:
            step(label, "already current", State.DONE)

    if not pending:
        note("nothing to do", "the monitoring surface is already in place")
        _record_state(set_config_values, state, dashboard=dashboard)
        return

    # New files are written outright; changed files go through the same
    # diff → overwrite/skip/view prompt every other Kaira surface uses.
    section("write")
    for plan in pending:
        if plan.status == "changed" and not (force or quiet) and is_interactive():
            show_diff(plan)
    written, skipped = apply_plan(pending, force=force, quiet=quiet)
    step("files", f"{written} written · {skipped} skipped", State.DONE)

    section("wire")
    if _ensure_requirement(root):
        step("requirements", _PROMETHEUS_REQUIREMENT, State.DONE)
    else:
        note("requirements", "prometheus-client already listed or no requirements.txt")

    main_path = root / "main.py"
    if not main_path.is_file():
        note("main.py", "not found — register the routers yourself")
    else:
        main_content = main_path.read_text(encoding="utf-8")
        if "KairaApp" in main_content or "KhairaApp" in main_content:
            current_providers = list(getattr(cfg, "providers", ["cache", "auth"]))
            if "monitor" not in current_providers:
                current_providers.append("monitor")
                set_config_values(providers=current_providers)
            step(
                "main.py",
                "KairaApp auto-discovers probes router and loads MonitorProvider",
                State.DONE,
            )
        elif _METRICS_CALL not in main_content:
            note("main.py", "left unchanged — add these two lines yourself:")
            subtext(_METRICS_CALL)
            subtext(_PROBES_INCLUDE)
        else:
            step(
                "main.py",
                "metrics middleware after security · probes registered",
                State.DONE,
            )

    if dashboard:
        _wire_dashboard_env(root, strategy)

    _record_state(set_config_values, state, dashboard=dashboard)
    append_history(
        "monitor init",
        {"dashboard": str(dashboard), "auth": strategy or "none"},
    )

    routes = [METRICS_ROUTE, LIVENESS_ROUTE, READINESS_ROUTE]
    if dashboard:
        routes.append(MONITOR_NAMESPACE)
    panel(
        f"[{Theme.SUCCESS}]Monitoring scaffolded.[/{Theme.SUCCESS}]\n\n"
        f"New routes: [{Theme.PRIMARY}]{'  '.join(routes)}[/{Theme.PRIMARY}]\n"
        f"[{Theme.MUTED}]/health is unchanged — Docker's HEALTHCHECK still points at it.[/{Theme.MUTED}]\n"
        f"[{Theme.MUTED}]Metrics are per-process; under multiple workers the dashboard\n"
        f"shows one worker's view, not an aggregate.[/{Theme.MUTED}]",
        title="Monitor",
        border_style=Theme.BORDER_SUCCESS,
    )

    next_steps = [
        f"[{Theme.PRIMARY}]pip install -r requirements.txt[/{Theme.PRIMARY}] — installs prometheus-client",
        f"[{Theme.PRIMARY}]kaira run[/{Theme.PRIMARY}] then [{Theme.PRIMARY}]kaira monitor status[/{Theme.PRIMARY}]",
    ]
    if dashboard:
        next_steps.append(
            f"Set [{Theme.WARNING}]{ENV_MONITOR_ENABLED}=true[/{Theme.WARNING}] to switch the dashboard on"
        )
    next_steps.append(
        f"[{Theme.PRIMARY}]kaira guide monitor[/{Theme.PRIMARY}] — full walkthrough"
    )
    print_next_steps(next_steps, quiet=quiet)

    from kaira.core.docker_render import maybe_autosync

    maybe_autosync(quiet=quiet)


def replace_auth(state: MonitorState, strategy: str) -> MonitorState:
    """Return *state* with ``dashboard_auth`` set to *strategy*."""
    from dataclasses import replace

    return replace(state, dashboard=True, dashboard_auth=strategy)


def _resolve_auth_strategy(
    state: MonitorState, *, dashboard: bool, auth: Optional[str], quiet: bool
) -> str:
    """Decide which auth strategy gates the dashboard.

    There is no "public" answer. If a strategy cannot be established, the command
    stops rather than generating a page that reports route-level operational data
    to anyone who finds the URL.

    Args:
        state: Resolved monitoring state (knows whether an auth guard exists).
        dashboard: Whether ``--dashboard`` was passed.
        auth: The explicit ``--auth`` value, if any.
        quiet: Non-interactive mode.

    Returns:
        ``"reuse"``, ``"token"``, or ``""`` when no dashboard was requested.

    Raises:
        typer.Exit: When no strategy can be determined, or ``reuse`` is asked for
            in a project with no auth guard.
    """
    if not dashboard:
        return ""

    choice = (auth or "").strip().lower()
    if not choice:
        if quiet or not is_interactive():
            console.print(
                f"[{Theme.ERROR}]{escape(sym('FAIL'))} --dashboard needs --auth reuse|token "
                f"in non-interactive mode.[/{Theme.ERROR}]"
            )
            raise typer.Exit(1)
        from kaira.core import prompts

        choice = prompts.select(
            "How should the dashboard be protected?",
            [(name, description) for name, description in AUTH_STRATEGIES.items()],
            default=AUTH_REUSE if state.auth_guard else AUTH_TOKEN,
            flag="--auth reuse|token",
        )

    if choice not in AUTH_STRATEGIES:
        console.print(
            f"[{Theme.ERROR}]{escape(sym('FAIL'))} Unknown auth strategy '{choice}'. "
            f"Valid: {', '.join(AUTH_STRATEGIES)}[/{Theme.ERROR}]"
        )
        raise typer.Exit(1)

    if choice == AUTH_REUSE and not state.auth_guard:
        console.print(
            f"[{Theme.ERROR}]{escape(sym('FAIL'))} --auth reuse needs auth/dependencies.py.\n"
            f"  Run [{Theme.PRIMARY}]kaira auth generate jwt[/{Theme.PRIMARY}] first, "
            f"or use [{Theme.PRIMARY}]--auth token[/{Theme.PRIMARY}].[/{Theme.ERROR}]"
        )
        raise typer.Exit(1)

    return choice


def _wire_dashboard_env(root: Path, strategy: str) -> None:
    """Write the dashboard's env keys and settings fields."""
    _update_env_files(ENV_MONITOR_ENABLED, "false")
    step(
        ENV_MONITOR_ENABLED,
        "added to .env* (default false — dashboard off)",
        State.DONE,
    )

    if strategy == AUTH_TOKEN:
        existing = _read_env_value(ENV_MONITOR_TOKEN)
        token = existing or _generate_token()
        _update_env_files(ENV_MONITOR_TOKEN, token)
        # The token is a credential: it goes into .env and is never echoed.
        step(
            ENV_MONITOR_TOKEN,
            "reused existing value" if existing else "generated (see .env)",
            State.DONE,
        )

    if _add_settings_field(
        root,
        "    MONITOR_TRACES_SAMPLE_RATE: float = 0.2",
        "MONITOR_TRACES_SAMPLE_RATE",
    ):
        step("settings", "MONITOR_TRACES_SAMPLE_RATE added", State.DONE)


def _record_state(setter: Any, state: MonitorState, *, dashboard: bool) -> None:
    """Persist the monitoring flags into ``.kaira.json``."""
    setter(
        monitor_metrics=True,
        monitor_probes=True,
        monitor_dashboard=bool(dashboard or state.dashboard),
        monitor_dashboard_auth=state.dashboard_auth if dashboard else "",
        monitor_json_logs=True,
    )


# ---------------------------------------------------------------------------
# Third-party SDK wiring — called by `kaira integrate --provider monitor/...`
# ---------------------------------------------------------------------------

_SDK_IMPORT = "from core.monitor_sdk import init_monitoring"
_SDK_CALL = "init_monitoring()"
_LIFESPAN_ANCHOR = 'logger.debug("Starting up FastAPI application...")'

_SDK_BLOCK = (
    "\n    # Third-party monitoring SDK, wired by\n"
    "    # `kaira integrate --provider monitor/<provider>`. Returns False and\n"
    "    # logs one line when the credential is unset — never blocks startup.\n"
    f"    {_SDK_IMPORT}\n\n"
    f"    {_SDK_CALL}\n"
)


def splice_sdk_init(content: str) -> str:
    """No-op: Provider SDK is registered via KairaApp lifecycle hooks.

    Returns content unchanged. The monitoring provider handles SDK initialization
    through KairaApp's LifecycleManager at runtime.
    """
    return content


def wire_provider_sdk(
    root: Path, provider: str, *, quiet: bool = False, force: bool = False
) -> None:
    """Generate ``core/monitor_sdk.py`` and start it from the lifespan.

    Completes what ``kaira integrate --provider monitor/<provider>`` used to
    leave as a stub: the SDK was installed and the env keys written, but nothing
    ever called ``init()``. The ``main.py`` edit goes through the same
    diff/confirm prompt as every other Kaira rewrite.

    Args:
        root: Project output root.
        provider: ``sentry``, ``datadog`` or ``newrelic``.
        quiet: Non-interactive mode — apply without prompting.
        force: Overwrite a changed file without prompting.
    """
    if provider not in monitor_state.MONITOR_PROVIDERS:
        return

    sdk_path = root / monitor_state.SDK_FILE
    sdk_path.parent.mkdir(parents=True, exist_ok=True)
    plans = [_plan_for(sdk_path, render_sdk_module(provider, root.name))]

    main_path = root / "main.py"
    if main_path.is_file():
        try:
            current = main_path.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if current:
            plans.append(_plan_for(main_path, splice_sdk_init(current)))

    pending = [plan for plan in plans if plan.needs_write]
    if not pending:
        return

    for plan in pending:
        if plan.status == "changed" and not (force or quiet) and is_interactive():
            show_diff(plan)
    written, _ = apply_plan(pending, force=force, quiet=quiet)

    dev = monitor_state.sampling_default(provider, "development")
    prod = monitor_state.sampling_default(provider, "production")
    _add_settings_field(
        root,
        f"    # Trace sampling for {provider} — {dev} in development, {prod} in\n"
        f"    # production. A paid service is metered, so this is deliberately\n"
        f"    # not 1.0; raise it when you need full fidelity.\n"
        f"    MONITOR_TRACES_SAMPLE_RATE: float = {prod}",
        "MONITOR_TRACES_SAMPLE_RATE",
    )

    console.print(
        f"  [{Theme.SUCCESS}]{escape(sym('OK'))}[/{Theme.SUCCESS}] SDK initialisation wired "
        f"[{Theme.MUTED}]({written} file{'s' if written != 1 else ''} · "
        f"traces sampled at {prod} in production)[/{Theme.MUTED}]"
    )
    if _SDK_CALL not in (
        main_path.read_text(encoding="utf-8") if main_path.is_file() else ""
    ):
        console.print(
            f"  [{Theme.MUTED}]Add [/{Theme.MUTED}][{Theme.PRIMARY}]{_SDK_IMPORT}"
            f"[/{Theme.PRIMARY}][{Theme.MUTED}] and call {_SDK_CALL} in your "
            f"lifespan startup.[/{Theme.MUTED}]"
        )


# ---------------------------------------------------------------------------
# kaira monitor status
# ---------------------------------------------------------------------------


def _fetch_json(url: str, token: str, timeout: float) -> Optional[dict[str, Any]]:
    """GET *url* and return the decoded JSON body, or ``None`` on any failure."""
    try:
        import httpx

        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
        if response.status_code != 200:
            return None
        payload = response.json()
    except Exception:  # noqa: BLE001 - a probe reports, it does not raise
        return None
    return payload if isinstance(payload, dict) else None


_SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][\w:]*)(?P<labels>\{[^}]*\})?\s+(?P<value>[-\d.eE+]+)$"
)


def parse_prometheus(text: str) -> dict[str, Any]:
    """Build a minimal metrics payload from Prometheus exposition text.

    The fallback for ``watch``/``status`` when the dashboard is not enabled:
    ``/metrics`` is always available once ``monitor init`` has run, so the alert
    loop never depends on the Tier 2 opt-in.

    Args:
        text: Raw exposition output.

    Returns:
        ``{"totals": {...}, "latency": {"p95_ms": ...}}`` in the same shape the
        dashboard's JSON endpoint returns, so both paths feed one renderer.
    """
    requests_total = 0.0
    errors_total = 0.0
    buckets: dict[float, float] = {}
    duration_count = 0.0

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        labels = match.group("labels") or ""
        try:
            value = float(match.group("value"))
        except ValueError:
            continue

        if name == "kaira_requests_total":
            requests_total += value
        elif name == "kaira_errors_total":
            errors_total += value
        elif name == "kaira_request_duration_seconds_count":
            duration_count += value
        elif name == "kaira_request_duration_seconds_bucket":
            bound = re.search(r'le="([^"]+)"', labels)
            if not bound:
                continue
            edge = float("inf") if bound.group(1) == "+Inf" else float(bound.group(1))
            buckets[edge] = buckets.get(edge, 0.0) + value

    p95_ms = 0.0
    if buckets and duration_count:
        target = duration_count * 0.95
        for edge in sorted(buckets):
            if buckets[edge] >= target and edge != float("inf"):
                p95_ms = edge * 1000
                break

    return {
        "totals": {
            "requests_total": int(requests_total),
            "errors_total": int(errors_total),
            "requests_window": int(requests_total),
            "errors_window": int(errors_total),
            "error_rate": round(errors_total / requests_total, 4)
            if requests_total
            else 0.0,
        },
        "latency": {"p50_ms": 0.0, "p95_ms": round(p95_ms, 2), "p99_ms": 0.0},
        "source": "prometheus",
    }


def fetch_live_payload(
    base_url: str = DEFAULT_BASE_URL, timeout: float = 2.0
) -> Optional[dict[str, Any]]:
    """Return live metrics from the running app, or ``None`` when unreachable.

    Prefers the dashboard's JSON endpoint because it carries the full picture;
    falls back to parsing ``/metrics``, which needs no dashboard and no token.

    Args:
        base_url: Where the application is listening.
        timeout: Per-request timeout in seconds.

    Returns:
        A payload in dashboard shape, or ``None``.
    """
    token = _read_env_value(ENV_MONITOR_TOKEN)
    payload = _fetch_json(f"{base_url}{DASHBOARD_DATA_ROUTE}", token, timeout)
    if payload is not None:
        payload["source"] = "dashboard"
        return payload

    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base_url}{METRICS_ROUTE}")
        if response.status_code != 200:
            return None
    except Exception:  # noqa: BLE001 - a probe reports, it does not raise
        return None
    return parse_prometheus(response.text)


@app.command("status")
def monitor_status(
    url: Annotated[
        Optional[str],
        typer.Option(
            "--url",
            help="Base URL of the running application "
            "(default: the server kaira run started, else "
            f"{DEFAULT_BASE_URL}).",
        ),
    ] = None,
) -> None:
    """Show what monitoring is configured, and what is actually running.

    Two halves on purpose: what is on disk (a static fact) and what the running
    process reports (a live one). A project can be fully scaffolded and still be
    reporting nothing because it was never restarted.

    Examples
    --------
    kaira monitor status
    kaira monitor status --url http://127.0.0.1:9000
    """
    require_project()
    url = url or _default_base_url()
    state = monitor_state.resolve_state(Path.cwd())

    section("configured", state.project_name)
    rows = [
        ("metrics", _flag(state.metrics, f"{METRICS_ROUTE}")),
        ("probes", _flag(state.probes, f"{LIVENESS_ROUTE}  {READINESS_ROUTE}")),
        ("dashboard", _dashboard_status(state)),
        ("json logs", _flag(state.json_logs, "KAIRA_LOG_FORMAT=json")),
        ("provider", state.provider or f"[{Theme.MUTED}]none[/{Theme.MUTED}]"),
    ]
    kv_table(rows)

    if not state.enabled:
        panel(
            f"No monitoring scaffolded yet.\n\n"
            f"  [{Theme.PRIMARY}]kaira monitor init[/{Theme.PRIMARY}]              metrics + probes\n"
            f"  [{Theme.PRIMARY}]kaira monitor init --dashboard[/{Theme.PRIMARY}]  and the mini dashboard",
            title="Monitor Status",
            border_style=Theme.BORDER_WARNING,
        )
        return

    section("live", url)
    payload = fetch_live_payload(url)
    if payload is None:
        note("application", "not reachable — start it with kaira run")
        hint("kaira run")
        return

    totals = payload.get("totals", {})
    latency = payload.get("latency", {})
    scope = payload.get("scope", {})

    step("application", f"reachable via {payload.get('source', 'metrics')}", State.DONE)
    field("requests", str(totals.get("requests_window", 0)))
    rate = float(totals.get("error_rate", 0.0))
    field("error rate", f"{rate * 100:.2f}%  ({totals.get('errors_window', 0)} errors)")
    field(
        "latency",
        f"p50 {latency.get('p50_ms', 0)}ms · p95 {latency.get('p95_ms', 0)}ms "
        f"· p99 {latency.get('p99_ms', 0)}ms",
    )
    if scope.get("process_id"):
        field("scope", f"pid {scope['process_id']} · single process")
        subtext("Under multiple workers this is one worker's view, not an aggregate.")

    saved = monitor_state.save_snapshot(payload)
    if saved:
        note("snapshot", saved.name)
        hint("kaira monitor diff --since yesterday")


def _flag(enabled: bool, detail_text: str) -> str:
    """Render a boolean feature as a themed status cell."""
    if enabled:
        return f"[{Theme.SUCCESS}]{escape(sym('OK'))} {detail_text}[/{Theme.SUCCESS}]"
    return f"[{Theme.MUTED}]not scaffolded[/{Theme.MUTED}]"


def _dashboard_status(state: MonitorState) -> str:
    """Render the dashboard's configured state, loudly if it is unprotected."""
    if not state.dashboard:
        return f"[{Theme.MUTED}]not scaffolded[/{Theme.MUTED}]"
    if state.dashboard_public:
        return (
            f"[{Theme.ERROR}]{escape(sym('FAIL'))} scaffolded with no auth strategy — "
            f"re-run kaira monitor init --dashboard[/{Theme.ERROR}]"
        )
    live = os.getenv(ENV_MONITOR_ENABLED, "").strip().lower() in {"1", "true", "yes"}
    switch = (
        f"[{Theme.SUCCESS}]enabled[/{Theme.SUCCESS}]"
        if live
        else f"[{Theme.WARNING}]off ({ENV_MONITOR_ENABLED} not true)[/{Theme.WARNING}]"
    )
    return f"{MONITOR_NAMESPACE} · auth: {state.dashboard_auth} · {switch}"


# ---------------------------------------------------------------------------
# kaira monitor watch
# ---------------------------------------------------------------------------


def notify_desktop(title: str, message: str) -> bool:
    """Fire an OS notification, returning whether one was actually delivered.

    The default alert path deliberately needs no account, no webhook and no
    third-party service: the machine you are already sitting at can tell you.

    Args:
        title: Notification title.
        message: Notification body.

    Returns:
        True when a notifier was found and invoked.
    """
    system = platform.system()
    try:
        if system == "Darwin" and shutil.which("osascript"):
            script = (
                f"display notification {json.dumps(message)} "
                f"with title {json.dumps(title)}"
            )
            subprocess.run(  # nosec B603 - fixed binary, arguments are not shell-parsed
                ["osascript", "-e", script], check=False, capture_output=True
            )
            return True
        if system == "Linux" and shutil.which("notify-send"):
            subprocess.run(  # nosec B603 - fixed binary, arguments are not shell-parsed
                ["notify-send", title, message], check=False, capture_output=True
            )
            return True
        if system == "Windows" and shutil.which("powershell"):
            script = (
                "[void][System.Reflection.Assembly]::LoadWithPartialName("
                "'System.Windows.Forms');"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                "$n.Visible=$true;"
                f"$n.ShowBalloonTip(10000,{json.dumps(title)},{json.dumps(message)},"
                "[System.Windows.Forms.ToolTipIcon]::Warning)"
            )
            subprocess.run(  # nosec B603 - fixed binary, arguments are not shell-parsed
                ["powershell", "-NoProfile", "-Command", script],
                check=False,
                capture_output=True,
            )
            return True
    except OSError:
        return False
    return False


def post_webhook(url: str, title: str, message: str) -> bool:
    """POST an alert to a Discord/Slack-style incoming webhook.

    Optional by design — the default path is a local notification, so nobody has
    to stand up an alerting service to be told their error rate tripled.

    Args:
        url: The webhook URL. Never printed unmasked.
        title: Alert title.
        message: Alert body.

    Returns:
        True when the POST was accepted.
    """
    if not url:
        return False
    try:
        import httpx

        body = {"content": f"**{title}**\n{message}", "text": f"{title}\n{message}"}
        with httpx.Client(timeout=5.0) as client:
            response = client.post(url, json=body)
        return response.status_code < 400
    except Exception:  # noqa: BLE001 - an alert channel failing is not fatal
        return False


def evaluate_thresholds(
    payload: dict[str, Any], *, error_rate: float, p95_ms: float
) -> list[str]:
    """Return the human-readable breaches in *payload*.

    Args:
        payload: A dashboard-shaped metrics payload.
        error_rate: Error-rate ceiling as a fraction (``0.05`` = 5%).
        p95_ms: p95 latency ceiling in milliseconds.

    Returns:
        One string per breached threshold; empty when everything is within
        bounds.
    """
    breaches: list[str] = []
    totals = payload.get("totals", {})
    latency = payload.get("latency", {})

    observed_rate = float(totals.get("error_rate", 0.0) or 0.0)
    if observed_rate > error_rate:
        breaches.append(
            f"error rate {observed_rate * 100:.2f}% > {error_rate * 100:.2f}%"
        )

    observed_p95 = float(latency.get("p95_ms", 0.0) or 0.0)
    if p95_ms > 0 and observed_p95 > p95_ms:
        breaches.append(f"p95 {observed_p95:.0f}ms > {p95_ms:.0f}ms")

    for anomaly in payload.get("anomalies", []) or []:
        breaches.append(
            f"{anomaly.get('route')} running {anomaly.get('ratio')}× its own baseline"
        )
    return breaches


@app.command("watch")
def monitor_watch(
    url: Annotated[
        Optional[str],
        typer.Option(
            "--url",
            help="Base URL of the running application "
            "(default: the server kaira run started, else "
            f"{DEFAULT_BASE_URL}).",
        ),
    ] = None,
    interval: Annotated[
        int, typer.Option("--interval", help="Seconds between polls.")
    ] = 10,
    error_rate: Annotated[
        float,
        typer.Option("--error-rate", help="Alert above this error rate (0.05 = 5%)."),
    ] = _ALERT_ERROR_RATE,
    p95: Annotated[
        float, typer.Option("--p95", help="Alert above this p95 latency in ms.")
    ] = _ALERT_P95_MS,
    once: Annotated[
        bool, typer.Option("--once", help="Poll a single time and exit (CI-friendly).")
    ] = False,
) -> None:
    """Tail live metrics and alert when a threshold trips.

    Alerts go to a desktop notification by default — no alerting service, no
    account. Set ``KAIRA_MONITOR_WEBHOOK_URL`` to also POST to Discord or Slack.
    The webhook URL is a credential and is only ever printed masked.

    Examples
    --------
    kaira monitor watch
    kaira monitor watch --error-rate 0.02 --p95 500
    kaira monitor watch --once
    """
    require_project()
    url = url or _default_base_url()

    webhook = _read_env_value(ENV_MONITOR_WEBHOOK)
    section("watch", url)
    field("interval", f"{interval}s")
    field("thresholds", f"error rate > {error_rate * 100:.1f}%  ·  p95 > {p95:.0f}ms")
    field(
        "webhook", mask_webhook_url(webhook) or f"[{Theme.MUTED}]none[/{Theme.MUTED}]"
    )
    console.print()

    last_snapshot = 0.0
    firing: set[str] = set()

    try:
        while True:
            payload = fetch_live_payload(url)
            stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

            if payload is None:
                console.print(
                    f"  [{Theme.MUTED}]{stamp}[/{Theme.MUTED}]  "
                    f"[{Theme.WARNING}]unreachable[/{Theme.WARNING}]"
                )
            else:
                breaches = evaluate_thresholds(
                    payload, error_rate=error_rate, p95_ms=p95
                )
                _print_watch_line(stamp, payload, breaches)

                # Alert on the transition into a breach, not on every poll —
                # a threshold that stays tripped for an hour is one problem, not
                # 360 notifications.
                new = {text for text in breaches if text not in firing}
                if new:
                    title = f"Kaira · {Path.cwd().name}"
                    body = "\n".join(sorted(new))
                    delivered = notify_desktop(title, body)
                    if webhook:
                        delivered = post_webhook(webhook, title, body) or delivered
                    if not delivered:
                        console.print(
                            f"  [{Theme.MUTED}]no notifier available — alert shown above only"
                            f"[/{Theme.MUTED}]"
                        )
                firing = set(breaches)

                if time.time() - last_snapshot >= 60:
                    monitor_state.save_snapshot(payload)
                    last_snapshot = time.time()

            if once:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print(f"\n  [{Theme.MUTED}]Stopped.[/{Theme.MUTED}]")


def _print_watch_line(stamp: str, payload: dict[str, Any], breaches: list[str]) -> None:
    """Print one poll result as a single, status-coloured line."""
    totals = payload.get("totals", {})
    latency = payload.get("latency", {})
    rate = float(totals.get("error_rate", 0.0) or 0.0)
    style = Theme.ERROR if breaches else (Theme.WARNING if rate else Theme.SUCCESS)
    # sym()'s ASCII fallbacks ("[x]", "[ok]") are valid Rich markup tags.
    marker = escape(sym("FAIL") if breaches else sym("OK"))
    console.print(
        f"  [{Theme.MUTED}]{stamp}[/{Theme.MUTED}]  [{style}]{marker}[/{style}]  "
        f"{totals.get('requests_window', 0)} reqs  "
        f"{rate * 100:.2f}% errors  "
        f"p95 {latency.get('p95_ms', 0)}ms"
    )
    for text in breaches:
        console.print(f"      [{Theme.ERROR}]{text}[/{Theme.ERROR}]")


# ---------------------------------------------------------------------------
# kaira monitor diff
# ---------------------------------------------------------------------------


def diff_payloads(
    before: dict[str, Any], after: dict[str, Any]
) -> list[tuple[str, str, str, str]]:
    """Compare two snapshots into ``(label, before, after, direction)`` rows.

    ``direction`` is ``"up"``, ``"down"`` or ``"flat"`` — the caller decides
    whether up is good, because for requests it is and for error rate it is not.

    Args:
        before: The baseline snapshot payload.
        after: The newer snapshot payload.

    Returns:
        One row per compared metric, in reading order.
    """
    rows: list[tuple[str, str, str, str]] = []

    def compare(label: str, old: float, new: float, suffix: str = "") -> None:
        direction = "flat"
        if new > old:
            direction = "up"
        elif new < old:
            direction = "down"
        rows.append((label, f"{old:g}{suffix}", f"{new:g}{suffix}", direction))

    old_totals = before.get("totals", {})
    new_totals = after.get("totals", {})
    compare(
        "requests",
        float(old_totals.get("requests_window", 0) or 0),
        float(new_totals.get("requests_window", 0) or 0),
    )
    compare(
        "errors",
        float(old_totals.get("errors_window", 0) or 0),
        float(new_totals.get("errors_window", 0) or 0),
    )
    compare(
        "error rate",
        round(float(old_totals.get("error_rate", 0) or 0) * 100, 2),
        round(float(new_totals.get("error_rate", 0) or 0) * 100, 2),
        "%",
    )

    old_latency = before.get("latency", {})
    new_latency = after.get("latency", {})
    for key, label in (("p50_ms", "p50"), ("p95_ms", "p95"), ("p99_ms", "p99")):
        compare(
            label,
            float(old_latency.get(key, 0) or 0),
            float(new_latency.get(key, 0) or 0),
            "ms",
        )
    return rows


_WORSE_WHEN_UP = {"errors", "error rate", "p50", "p95", "p99"}


@app.command("diff")
def monitor_diff(
    since: Annotated[
        str,
        typer.Option(
            "--since",
            help="Baseline to compare against: yesterday | week | hour | today "
            "| an ISO timestamp.",
        ),
    ] = "yesterday",
) -> None:
    """Compare two saved metrics snapshots.

    Snapshots are written by ``kaira monitor status`` and, once a minute, by
    ``kaira monitor watch`` — so a diff only reaches as far back as you have been
    looking. Output uses the same ``+``/``-`` visual language as
    ``kaira sync model --dry-run`` and ``kaira docker sync --dry-run``.

    Examples
    --------
    kaira monitor diff
    kaira monitor diff --since week
    kaira monitor diff --since 2026-08-01T09:00:00Z
    """
    require_project()

    baseline_path, latest_path = monitor_state.find_snapshot_pair(since)
    if latest_path is None:
        panel(
            f"No snapshots recorded yet.\n\n"
            f"  [{Theme.PRIMARY}]kaira monitor status[/{Theme.PRIMARY}]  "
            f"takes one against a running app\n"
            f"  [{Theme.PRIMARY}]kaira monitor watch[/{Theme.PRIMARY}]   "
            f"takes one a minute while it runs",
            title="Monitor Diff",
            border_style=Theme.BORDER_WARNING,
        )
        return
    if baseline_path is None or baseline_path == latest_path:
        panel(
            f"Only one snapshot on file ([{Theme.PRIMARY}]{latest_path.name}"
            f"[/{Theme.PRIMARY}]).\nTake another one later, then diff.",
            title="Monitor Diff",
            border_style=Theme.BORDER_WARNING,
        )
        return

    before = monitor_state.load_snapshot(baseline_path)
    after = monitor_state.load_snapshot(latest_path)

    section("snapshots", f"since {since}")
    field("baseline", baseline_path.name)
    field("latest", latest_path.name)

    section("change")
    for label, old, new, direction in diff_payloads(before, after):
        if direction == "flat":
            console.print(f"  [{Theme.MUTED}]= {label:<12} {old}[/{Theme.MUTED}]")
            continue
        worse = (direction == "up") == (label in _WORSE_WHEN_UP)
        style = Theme.ERROR if worse else Theme.SUCCESS
        marker = "+" if direction == "up" else "-"
        console.print(f"  [{style}]{marker} {label:<12} {old} → {new}[/{style}]")

    _diff_routes(before, after)
    _diff_markers(before, after)


def _diff_routes(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Print routes that appeared, disappeared, or changed p95 between snapshots."""

    def by_route(payload: dict[str, Any]) -> dict[str, float]:
        rows = (payload.get("routes", {}) or {}).get("by_latency", []) or []
        return {str(row["route"]): float(row.get("p95_ms", 0)) for row in rows}

    old, new = by_route(before), by_route(after)
    if not old and not new:
        return

    section("routes", "by p95")
    for route in sorted(set(old) | set(new)):
        if route not in old:
            console.print(
                f"  [{Theme.SUCCESS}]+ {route}  {new[route]}ms[/{Theme.SUCCESS}]"
            )
        elif route not in new:
            console.print(
                f"  [{Theme.MUTED}]- {route}  (no longer in top routes)[/{Theme.MUTED}]"
            )
        elif abs(new[route] - old[route]) >= 1:
            worse = new[route] > old[route]
            style = Theme.ERROR if worse else Theme.SUCCESS
            console.print(
                f"  [{style}]{'+' if worse else '-'} {route}  "
                f"{old[route]}ms → {new[route]}ms[/{style}]"
            )


def _diff_markers(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Print the Kaira operations that happened between the two snapshots."""
    old = {
        (marker.get("command"), marker.get("at"))
        for marker in before.get("markers", []) or []
    }
    new = [
        marker
        for marker in after.get("markers", []) or []
        if (marker.get("command"), marker.get("at")) not in old
    ]
    if not new:
        return
    section("between", "what changed in the project")
    for marker in new:
        console.print(
            f"  [{Theme.ACCENT}]· kaira {marker.get('command')}[/{Theme.ACCENT}]  "
            f"[{Theme.MUTED}]{marker.get('at')}[/{Theme.MUTED}]"
        )
