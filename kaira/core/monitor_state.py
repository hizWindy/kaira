"""Monitoring project-state resolution — the single source of truth for
``kaira monitor``.

Like :mod:`kaira.core.docker_state`, this module is deliberately free of Rich,
Typer, and Jinja imports: it is pure state, so any command can import it without
circularity and it can be unit tested without a terminal.

What lives here
---------------

``MonitorState``
    The normalised snapshot every ``kaira monitor`` command and every generated
    monitoring file renders from.  Resolved from ``.kaira.json`` first, falling
    back to filesystem detection for projects scaffolded before the flags
    existed.

``GENERATED_FILES``
    Which file each monitoring feature owns.  ``kaira monitor init`` builds its
    plan by looping over this mapping, so adding a feature later is one entry
    here rather than a new branch in the command.

Standing constraints this module encodes
----------------------------------------
* ``/health`` is never in any list here.  Phase 4 owns that route; this phase
  only ever *adds* ``/healthz``, ``/readyz`` and ``/metrics`` beside it.
* Internal routes mount under the reserved ``/_kaira/monitor`` namespace so they
  can never collide with a user's own ``/api/v1/*`` routes.
* The dashboard is off unless ``KAIRA_MONITOR_ENABLED=true`` *and* an auth
  strategy was chosen — "not configured" resolves to "disabled", never "public".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Reserved namespace and routes
# ---------------------------------------------------------------------------

MONITOR_NAMESPACE = "/_kaira/monitor"
"""Reserved mount point for Kaira's own operational routes.

Deliberately not a bare ``/monitor``: a generated project owns ``/api/v1/*`` and
its root, and a future user model called ``Monitor`` would otherwise collide
with Kaira's dashboard.
"""

DASHBOARD_ROUTE = MONITOR_NAMESPACE
DASHBOARD_DATA_ROUTE = f"{MONITOR_NAMESPACE}/data"

METRICS_ROUTE = "/metrics"
LIVENESS_ROUTE = "/healthz"
READINESS_ROUTE = "/readyz"

HEALTH_ROUTE = "/health"
"""Phase 4's endpoint.  Listed only so tests can assert it is never touched."""

PROBE_ROUTES = (LIVENESS_ROUTE, READINESS_ROUTE)
PUBLIC_ROUTES = (METRICS_ROUTE, LIVENESS_ROUTE, READINESS_ROUTE)
"""Unauthenticated by design — a scraper and a kubelet have no credentials.

They carry counts, timings and a literal ``ok``/``not ready``; never a DSN, a
secret, or a stack trace.
"""

PROBE_RATE_LIMIT = "300/minute"
"""Matches the Phase 4 ``/health`` limit so probes never trigger a 429."""

# ---------------------------------------------------------------------------
# Environment contract
# ---------------------------------------------------------------------------

ENV_LOG_FORMAT = "KAIRA_LOG_FORMAT"
ENV_MONITOR_ENABLED = "KAIRA_MONITOR_ENABLED"
ENV_MONITOR_TOKEN = "KAIRA_MONITOR_TOKEN"  # nosec B105 - env var name, not a secret
ENV_MONITOR_WEBHOOK = "KAIRA_MONITOR_WEBHOOK_URL"

MONITOR_ENV_KEYS = (ENV_MONITOR_ENABLED, ENV_MONITOR_TOKEN)
"""Keys ``kaira monitor init --dashboard`` writes into ``.env*``."""

# ---------------------------------------------------------------------------
# Dashboard auth strategies
# ---------------------------------------------------------------------------

AUTH_REUSE = "reuse"
AUTH_TOKEN = "token"
AUTH_DISABLED = ""

AUTH_STRATEGIES: dict[str, str] = {
    AUTH_REUSE: "Reuse the project's existing auth guard (auth/dependencies.py)",
    AUTH_TOKEN: f"Standalone bearer token from {ENV_MONITOR_TOKEN}",
}
"""Selectable strategies for the dashboard gate.

There is no "public" option.  ``/health`` is public because it says almost
nothing; the dashboard reports per-route traffic, error rates and dependency
state, which is operational intelligence about a running system.
"""

# ---------------------------------------------------------------------------
# Cost-conscious third-party sampling defaults
# ---------------------------------------------------------------------------

PROVIDER_SAMPLING: dict[str, dict[str, float]] = {
    "sentry": {"development": 1.0, "production": 0.2},
    "datadog": {"development": 1.0, "production": 0.2},
    "newrelic": {"development": 1.0, "production": 0.2},
}
"""``provider`` → environment → trace sample rate.

These are paid services with metered free tiers, so a generated project samples
rather than shipping every transaction.  The rendered value lands in ``settings``
as ``MONITOR_TRACES_SAMPLE_RATE``, never hardcoded at the call site, so a project
that wants full fidelity changes one field.
"""

MONITOR_PROVIDERS = tuple(PROVIDER_SAMPLING)


def sampling_default(provider: str, app_env: str = "production") -> float:
    """Return the default trace sample rate for *provider* in *app_env*.

    Args:
        provider: ``sentry``, ``datadog`` or ``newrelic``.
        app_env: Deployment environment name.

    Returns:
        The sample rate in ``0.0..1.0``; ``0.2`` for an unknown provider, which
        is the conservative choice when Kaira does not know the pricing model.
    """
    rates = PROVIDER_SAMPLING.get(provider.lower(), {})
    return rates.get(app_env.lower(), rates.get("production", 0.2))


# ---------------------------------------------------------------------------
# In-memory window sizing (mirrored by the generated core/metrics.py)
# ---------------------------------------------------------------------------

WINDOW_MINUTES = 60
"""Per-minute buckets retained by the generated rolling window."""

BASELINE_DAYS = 7
"""Daily p95 buckets retained per route for the self-baseline anomaly flag."""

ANOMALY_FACTOR = 1.5
"""How far above its own baseline a route's p95 must run to be flagged."""

# ---------------------------------------------------------------------------
# Generated files
# ---------------------------------------------------------------------------

FEATURE_METRICS = "metrics"
FEATURE_PROBES = "probes"
FEATURE_DASHBOARD = "dashboard"
FEATURE_LOGS = "logs"

GENERATED_FILES: dict[str, tuple[str, str]] = {
    FEATURE_METRICS: ("core/metrics.py", "monitor_metrics.py.j2"),
    "middleware": ("middleware/metrics.py", "monitor_middleware.py.j2"),
    FEATURE_PROBES: ("routers/probes_router.py", "monitor_probes_router.py.j2"),
    "dashboard_view": ("core/monitor_dashboard.py", "monitor_dashboard.py.j2"),
    FEATURE_DASHBOARD: ("routers/monitor_router.py", "monitor_router.py.j2"),
}
"""``feature key`` → ``(project-relative path, Jinja template name)``.

``kaira monitor init`` loops over this mapping to build its file plan, so the
command has no per-file branch and a future monitoring file is one entry here.
"""

SDK_FILE = "core/monitor_sdk.py"
SDK_TEMPLATE = "monitor_sdk.py.j2"
"""Written by ``kaira integrate --provider monitor/<provider>``, not by
``monitor init`` — Tier 1 never requires a provider account."""

TIER1_FEATURES = (FEATURE_METRICS, "middleware", FEATURE_PROBES)
TIER2_FEATURES = ("dashboard_view", FEATURE_DASHBOARD)

SNAPSHOT_DIR = Path(".kaira") / "monitor"
"""Where ``kaira monitor status``/``watch`` persist snapshots for ``monitor diff``.

Under the existing ``.kaira/`` state directory that already holds
``history.jsonl`` — monitoring introduces no new top-level path in a user's
project, and no log files (see the standing terminal-only logging rule).
"""

SNAPSHOT_SUFFIX = ".json"

CHANGE_MARKER_COMMANDS = (
    "migrate run",
    "migrate make",
    "sync model",
    "deploy run",
    "docker sync",
    "monitor init",
)
"""History commands worth overlaying on the dashboard's latency timeline.

Read-only consumption of ``.kaira/history.jsonl``, which Kaira has written since
Phase 4 — this phase adds no logging surface to produce them.
"""


# ---------------------------------------------------------------------------
# Secret masking
# ---------------------------------------------------------------------------

_WEBHOOK_RE = re.compile(r"^(https?://)([^/]+)(/.*)?$", re.IGNORECASE)


def mask_webhook_url(url: str) -> str:
    """Return *url* with its secret path masked, safe to print.

    A Discord or Slack incoming-webhook URL *is* the credential: whoever has the
    full path can post as the integration.  Only the scheme and host survive::

        https://hooks.slack.com/services/T00/B00/XXXX
        -> https://hooks.slack.com/***

    Args:
        url: Raw webhook URL, possibly empty.

    Returns:
        The masked form, or ``""`` when *url* is empty.
    """
    if not url:
        return ""
    match = _WEBHOOK_RE.match(url.strip())
    if not match:
        return "***"
    scheme, host, path = match.groups()
    return f"{scheme}{host}/***" if path else f"{scheme}{host}"


# ---------------------------------------------------------------------------
# Project state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonitorState:
    """Normalised snapshot of a project's monitoring surface."""

    project_name: str
    metrics: bool = False
    probes: bool = False
    dashboard: bool = False
    dashboard_auth: str = AUTH_DISABLED
    json_logs: bool = False
    provider: str = ""
    cache: bool = False
    task: bool = False
    db_type: str = "sqlite"
    api_version: str = "v1"
    auth_guard: bool = False

    @property
    def enabled(self) -> bool:
        """True once any part of the monitoring surface has been scaffolded."""
        return bool(self.metrics or self.probes or self.dashboard)

    @property
    def dashboard_public(self) -> bool:
        """True only if a dashboard exists with no auth strategy recorded.

        Always False for anything ``kaira monitor init`` generates — it exists so
        ``monitor status`` can shout if a hand-edited project ever reaches that
        state.
        """
        return self.dashboard and not self.dashboard_auth

    @property
    def features(self) -> list[str]:
        """Human-readable names of the enabled monitoring features."""
        names: list[str] = []
        if self.metrics:
            names.append("metrics (/metrics)")
        if self.probes:
            names.append("probes (/healthz, /readyz)")
        if self.dashboard:
            names.append(f"dashboard ({MONITOR_NAMESPACE})")
        if self.json_logs:
            names.append("json logs")
        if self.provider:
            names.append(f"provider ({self.provider})")
        return names


# ---------------------------------------------------------------------------
# Filesystem detection
# ---------------------------------------------------------------------------


def detect_metrics(root: Path) -> bool:
    """True when the metrics module has been scaffolded in *root*."""
    return (root / "core" / "metrics.py").is_file()


def detect_probes(root: Path) -> bool:
    """True when the liveness/readiness router has been scaffolded in *root*."""
    return (root / "routers" / "probes_router.py").is_file()


def detect_dashboard(root: Path) -> bool:
    """True when the mini dashboard has been scaffolded in *root*."""
    return (root / "routers" / "monitor_router.py").is_file()


def detect_auth_guard(root: Path) -> bool:
    """True when the project has an auth dependency the dashboard can reuse."""
    return (root / "auth" / "dependencies.py").is_file()


def detect_json_logs(root: Path) -> bool:
    """True when the generated logger understands ``KAIRA_LOG_FORMAT=json``."""
    logger_path = root / "core" / "logger.py"
    if not logger_path.is_file():
        return False
    try:
        return ENV_LOG_FORMAT in logger_path.read_text(encoding="utf-8")
    except OSError:
        return False


def resolve_state(root: Optional[Path] = None) -> MonitorState:
    """Build the :class:`MonitorState` for the project rooted at *root*.

    Explicit ``.kaira.json`` flags win; filesystem detection fills the gaps so a
    project that predates those flags still reports accurately.

    Args:
        root: Project root; defaults to the current working directory.

    Returns:
        The resolved monitoring state.
    """
    from kaira.config import get_config

    root = Path.cwd() if root is None else root
    cfg = get_config()
    output_root = root / (cfg.output_dir or ".")

    dashboard = bool(getattr(cfg, "monitor_dashboard", False)) or detect_dashboard(
        output_root
    )
    recorded_auth = str(getattr(cfg, "monitor_dashboard_auth", "") or "")

    return MonitorState(
        project_name=root.name,
        metrics=bool(getattr(cfg, "monitor_metrics", False))
        or detect_metrics(output_root),
        probes=bool(getattr(cfg, "monitor_probes", False))
        or detect_probes(output_root),
        dashboard=dashboard,
        dashboard_auth=recorded_auth if dashboard else AUTH_DISABLED,
        json_logs=bool(getattr(cfg, "monitor_json_logs", False))
        or detect_json_logs(output_root),
        provider=(getattr(cfg, "monitor_provider", "") or "").lower(),
        cache=bool(getattr(cfg, "cache_enabled", False))
        or (output_root / "core" / "cache.py").is_file(),
        task=bool(getattr(cfg, "task_enabled", False))
        or (output_root / "tasks" / "celery_app.py").is_file(),
        db_type=(cfg.db_type or "sqlite").lower(),
        api_version=cfg.api_version or "v1",
        auth_guard=detect_auth_guard(output_root),
    )


def build_context(state: MonitorState) -> dict[str, Any]:
    """Return the Jinja context every monitoring template renders from."""
    return {
        "project_name": state.project_name,
        "db_type": state.db_type,
        "api_version": state.api_version,
        "cache_enabled": state.cache,
        "task_enabled": state.task,
        "dashboard_auth": state.dashboard_auth,
        "auth_guard": state.auth_guard and state.dashboard_auth == AUTH_REUSE,
        "monitor_namespace": MONITOR_NAMESPACE,
        "metrics_route": METRICS_ROUTE,
        "liveness_route": LIVENESS_ROUTE,
        "readiness_route": READINESS_ROUTE,
        "probe_rate_limit": PROBE_RATE_LIMIT,
        "window_minutes": WINDOW_MINUTES,
        "baseline_days": BASELINE_DAYS,
        "anomaly_factor": ANOMALY_FACTOR,
        "env_enabled": ENV_MONITOR_ENABLED,
        "env_token": ENV_MONITOR_TOKEN,
        "change_marker_commands": list(CHANGE_MARKER_COMMANDS),
    }


# ---------------------------------------------------------------------------
# Snapshots — the persistence behind `kaira monitor diff`
# ---------------------------------------------------------------------------


def snapshot_dir(root: Optional[Path] = None) -> Path:
    """Return the snapshot directory for the project rooted at *root*."""
    root = Path.cwd() if root is None else root
    return root / SNAPSHOT_DIR


def save_snapshot(
    payload: dict[str, Any], root: Optional[Path] = None
) -> Optional[Path]:
    """Persist one metrics *payload* for later comparison.

    Snapshots are the only thing this phase writes to disk at runtime, and they
    are metric aggregates — counts, timings, route templates.  Never request
    bodies, headers, or user data.

    Args:
        payload: The ``/_kaira/monitor/data`` payload (or an equivalent built
            from ``/metrics``).
        root: Project root; defaults to the current working directory.

    Returns:
        The written path, or ``None`` when the project directory is not
        writable — a failed snapshot must never break the command that took it.
    """
    directory = snapshot_dir(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"{stamp}{SNAPSHOT_SUFFIX}"
    record = dict(payload)
    record.setdefault("captured_at", datetime.now(timezone.utc).isoformat())
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    except OSError:
        return None
    return path


def list_snapshots(root: Optional[Path] = None) -> list[Path]:
    """Return every stored snapshot, oldest first."""
    directory = snapshot_dir(root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"*{SNAPSHOT_SUFFIX}"))


def load_snapshot(path: Path) -> dict[str, Any]:
    """Load one snapshot file, returning ``{}`` when it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_RELATIVE_SINCE = {
    "now": timedelta(0),
    "hour": timedelta(hours=1),
    "today": timedelta(hours=12),
    "yesterday": timedelta(days=1),
    "week": timedelta(days=7),
}


def parse_since(value: str) -> Optional[datetime]:
    """Resolve a ``--since`` value to an aware UTC datetime.

    Accepts the words in :data:`_RELATIVE_SINCE` (``yesterday``, ``week``, …) or
    an ISO-8601 timestamp.

    Args:
        value: The raw ``--since`` string.

    Returns:
        The resolved instant, or ``None`` when *value* is not understood.
    """
    text = (value or "").strip().lower()
    if not text:
        return None
    if text in _RELATIVE_SINCE:
        return datetime.now(timezone.utc) - _RELATIVE_SINCE[text]
    try:
        parsed = datetime.fromisoformat(text.replace("z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def snapshot_time(path: Path) -> Optional[datetime]:
    """Return the capture instant encoded in a snapshot filename."""
    try:
        return datetime.strptime(path.stem, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def find_snapshot_pair(
    since: str, root: Optional[Path] = None
) -> tuple[Optional[Path], Optional[Path]]:
    """Return ``(baseline, latest)`` snapshots for a ``--since`` value.

    The baseline is the newest snapshot taken at or before the resolved instant,
    falling back to the oldest snapshot on file so a young project still gets a
    comparison instead of an error.

    Args:
        since: A ``--since`` value such as ``yesterday``.
        root: Project root; defaults to the current working directory.

    Returns:
        ``(baseline, latest)``; either may be ``None`` when there is nothing to
        compare.
    """
    snapshots = list_snapshots(root)
    if len(snapshots) < 2:
        return (None, snapshots[0] if snapshots else None)

    latest = snapshots[-1]
    cutoff = parse_since(since)
    if cutoff is None:
        return (snapshots[-2], latest)

    older = [
        path
        for path in snapshots[:-1]
        if (stamp := snapshot_time(path)) is not None and stamp <= cutoff
    ]
    return (older[-1] if older else snapshots[0], latest)
