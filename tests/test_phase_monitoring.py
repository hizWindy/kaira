"""Tests for the monitoring phase — state, templates, wiring, and CLI.

Two things these tests care about more than anything else, because they are the
promises the phase was built on:

* ``/health`` comes out the other side untouched — same route, same response
  shape, same absence of an auth dependency.
* The security middleware keeps its registration position, and the metrics
  middleware is always registered after it.

Both get explicit regression tests below (``TestNonDisruptive``).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
from typer.testing import CliRunner

from kaira.commands import monitor_cmd
from kaira.core import docker_state, monitor_state
from kaira.core.monitor_state import MonitorState
from kaira.main import app

runner = CliRunner()

TEMPLATES = Path(__file__).parent.parent / "kaira" / "templates"


def run(*args):
    """Invoke the kaira CLI with the given arguments."""
    return runner.invoke(app, list(args))


def jinja() -> Environment:
    """Return the same Jinja environment the commands render with."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def make_state(**overrides) -> MonitorState:
    """Build a MonitorState with sensible test defaults."""
    base = {"project_name": "demo-api", "db_type": "sqlite", "api_version": "v1"}
    base.update(overrides)
    return MonitorState(**base)


def write_project(root: Path, **config) -> None:
    """Write a minimal .kaira.json into *root*."""
    data = {"output_dir": ".", "db_type": "sqlite", "api_version": "v1"}
    data.update(config)
    (root / ".kaira.json").write_text(json.dumps(data), encoding="utf-8")


def scaffold_project(root: Path) -> None:
    """Render just enough of a generated project for `monitor init` to wire it."""
    write_project(root)
    env = jinja()
    (root / "main.py").write_text(
        env.get_template("main_app_v3.py.j2").render(
            project_name="demo-api", db_type="sqlite", api_version="v1"
        ),
        encoding="utf-8",
    )
    (root / "core").mkdir(exist_ok=True)
    (root / "core" / "logger.py").write_text(
        env.get_template("logger.py.j2").render(project_name="demo-api"),
        encoding="utf-8",
    )
    (root / "config").mkdir(exist_ok=True)
    (root / "config" / "settings.py").write_text(
        "class Settings:\n    APP_ENV: str = 'development'\n", encoding="utf-8"
    )
    (root / "requirements.txt").write_text("fastapi>=0.115.0\n", encoding="utf-8")
    (root / ".env").write_text("APP_ENV=development\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure state
# ---------------------------------------------------------------------------


class TestMonitorState:
    def test_reserved_namespace_is_not_a_bare_path(self):
        # A bare /monitor would collide with a user model called Monitor.
        assert monitor_state.MONITOR_NAMESPACE.startswith("/_kaira/")
        assert monitor_state.DASHBOARD_DATA_ROUTE.startswith(
            monitor_state.MONITOR_NAMESPACE
        )

    def test_health_is_never_a_probe_route(self):
        assert monitor_state.HEALTH_ROUTE not in monitor_state.PROBE_ROUTES
        assert monitor_state.HEALTH_ROUTE not in monitor_state.PUBLIC_ROUTES

    def test_probe_rate_limit_matches_health(self):
        # Phase 4 rate-limits /health at 300/minute; probes must not be stricter
        # or a 1-second probe interval starts 429-ing.
        assert monitor_state.PROBE_RATE_LIMIT == "300/minute"

    @pytest.mark.parametrize("provider", monitor_state.MONITOR_PROVIDERS)
    def test_production_sampling_is_cost_conscious(self, provider):
        prod = monitor_state.sampling_default(provider, "production")
        dev = monitor_state.sampling_default(provider, "development")
        assert 0 < prod < 1.0, "production must not send every trace"
        assert dev == 1.0, "development should not be sampled"

    def test_unknown_provider_falls_back_to_conservative_rate(self):
        assert monitor_state.sampling_default("mystery") == 0.2

    def test_no_public_auth_strategy_exists(self):
        assert "public" not in monitor_state.AUTH_STRATEGIES
        assert set(monitor_state.AUTH_STRATEGIES) == {"reuse", "token"}

    def test_dashboard_without_auth_reads_as_public_and_is_flagged(self):
        state = make_state(dashboard=True, dashboard_auth="")
        assert state.dashboard_public is True

    def test_dashboard_with_auth_is_not_public(self):
        state = make_state(dashboard=True, dashboard_auth="token")
        assert state.dashboard_public is False

    @pytest.mark.parametrize(
        "url,expected",
        [
            (
                "https://hooks.slack.com/services/T00/B00/XXXX",
                "https://hooks.slack.com/***",
            ),
            ("https://discord.com/api/webhooks/1/secret", "https://discord.com/***"),
            ("https://example.com", "https://example.com"),
            ("", ""),
            ("not-a-url", "***"),
        ],
    )
    def test_webhook_masking(self, url, expected):
        assert monitor_state.mask_webhook_url(url) == expected

    def test_resolve_detects_scaffolded_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "metrics.py").write_text("", encoding="utf-8")
        (tmp_path / "routers").mkdir()
        (tmp_path / "routers" / "probes_router.py").write_text("", encoding="utf-8")

        state = monitor_state.resolve_state(tmp_path)
        assert state.metrics is True
        assert state.probes is True
        assert state.dashboard is False

    def test_resolve_prefers_recorded_flags(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path, monitor_metrics=True, monitor_probes=True)
        state = monitor_state.resolve_state(tmp_path)
        assert state.metrics is True and state.probes is True


class TestSnapshots:
    def test_save_and_load_roundtrip(self, tmp_path):
        path = monitor_state.save_snapshot({"totals": {"requests_window": 5}}, tmp_path)
        assert path is not None
        loaded = monitor_state.load_snapshot(path)
        assert loaded["totals"]["requests_window"] == 5
        assert "captured_at" in loaded

    def test_snapshots_live_under_the_existing_kaira_dir(self, tmp_path):
        monitor_state.save_snapshot({}, tmp_path)
        assert (tmp_path / ".kaira" / "monitor").is_dir()

    def test_load_returns_empty_for_corrupt_file(self, tmp_path):
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        assert monitor_state.load_snapshot(broken) == {}

    @pytest.mark.parametrize("value", ["yesterday", "week", "hour", "today"])
    def test_parse_since_relative_words(self, value):
        assert monitor_state.parse_since(value) is not None

    def test_parse_since_iso(self):
        parsed = monitor_state.parse_since("2026-08-01T09:00:00Z")
        assert parsed is not None and parsed.year == 2026

    def test_parse_since_rejects_nonsense(self):
        assert monitor_state.parse_since("banana") is None

    def test_find_pair_picks_baseline_before_cutoff(self, tmp_path):
        directory = tmp_path / ".kaira" / "monitor"
        directory.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        for offset in (72, 36, 0):
            stamp = (now - timedelta(hours=offset)).strftime("%Y%m%dT%H%M%SZ")
            (directory / f"{stamp}.json").write_text("{}", encoding="utf-8")

        baseline, latest = monitor_state.find_snapshot_pair("yesterday", tmp_path)
        assert baseline is not None and latest is not None
        assert baseline != latest
        baseline_at = monitor_state.snapshot_time(baseline)
        assert baseline_at is not None
        assert baseline_at <= now - timedelta(hours=23)

    def test_find_pair_with_a_single_snapshot(self, tmp_path):
        monitor_state.save_snapshot({}, tmp_path)
        baseline, latest = monitor_state.find_snapshot_pair("yesterday", tmp_path)
        assert baseline is None and latest is not None


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestRendering:
    @pytest.mark.parametrize("dashboard", [False, True])
    def test_every_generated_module_is_valid_python(self, dashboard):
        state = make_state(
            dashboard=dashboard, dashboard_auth="token" if dashboard else ""
        )
        files = monitor_cmd.render_monitor_files(state, dashboard=dashboard)
        for name, source in files.items():
            ast.parse(source, filename=name)

    def test_tier1_renders_three_modules(self):
        files = monitor_cmd.render_monitor_files(make_state(), dashboard=False)
        assert set(files) == {
            "core/metrics.py",
            "middleware/metrics.py",
            "routers/probes_router.py",
        }

    def test_dashboard_adds_exactly_two_modules(self):
        tier1 = monitor_cmd.render_monitor_files(make_state(), dashboard=False)
        state = make_state(dashboard=True, dashboard_auth="token")
        tier2 = monitor_cmd.render_monitor_files(state, dashboard=True)
        assert set(tier2) - set(tier1) == {
            "core/monitor_dashboard.py",
            "routers/monitor_router.py",
        }

    def test_probes_router_never_defines_health(self):
        files = monitor_cmd.render_monitor_files(make_state(), dashboard=False)
        source = files["routers/probes_router.py"]
        assert '"/healthz"' in source or "'/healthz'" in source
        assert "/readyz" in source
        # The only mentions of /health are in prose explaining that it is
        # untouched — never in a route decorator.
        tree = ast.parse(source)
        decorated_paths = [
            arg.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for arg in node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        ]
        assert "/health" not in decorated_paths

    def test_metrics_module_uses_route_template_labels_only(self):
        source = monitor_cmd.render_monitor_files(make_state(), dashboard=False)[
            "core/metrics.py"
        ]
        assert 'Counter(\n    "kaira_requests_total"' in source
        assert '"kaira_request_duration_seconds"' in source
        assert '"kaira_errors_total"' in source
        # Labels are method/path/status — never a user id, body, or header.
        assert '["method", "path", "status"]' in source

    def test_middleware_reads_the_existing_timing_header(self):
        source = monitor_cmd.render_monitor_files(make_state(), dashboard=False)[
            "middleware/metrics.py"
        ]
        assert "X-Response-Time" in source, (
            "the metrics middleware must reuse the security middleware's timing"
        )

    @pytest.mark.parametrize("strategy", ["token", "reuse"])
    def test_dashboard_router_is_gated(self, strategy):
        state = make_state(
            dashboard=True, dashboard_auth=strategy, auth_guard=strategy == "reuse"
        )
        source = monitor_cmd.render_monitor_files(state, dashboard=True)[
            "routers/monitor_router.py"
        ]
        assert monitor_state.ENV_MONITOR_ENABLED in source
        if strategy == "token":
            assert "secrets.compare_digest" in source
            assert "import secrets" in source
        else:
            assert "get_current_user" in source
            assert "import secrets" not in source

    def test_dashboard_router_without_a_strategy_stays_closed(self):
        state = make_state(dashboard=True, dashboard_auth="")
        source = monitor_cmd.render_monitor_files(state, dashboard=True)[
            "routers/monitor_router.py"
        ]
        # No strategy recorded means the guard raises unconditionally.
        assert "HTTP_404_NOT_FOUND" in source
        assert "compare_digest" not in source

    def test_dashboard_html_has_no_external_requests(self):
        state = make_state(dashboard=True, dashboard_auth="token")
        source = monitor_cmd.render_monitor_files(state, dashboard=True)[
            "core/monitor_dashboard.py"
        ]
        for host in ("googleapis.com", "unpkg.com", "jsdelivr.net", "cdnjs."):
            assert host not in source, f"the dashboard reaches out to {host}"
        assert "<script src=" not in source
        assert '<link rel="stylesheet"' not in source
        assert "@import" not in source
        # The only absolute URL allowed is the SVG namespace, which is an XML
        # identifier rather than something the browser fetches.
        urls = re.findall(r"https?://[^\s\"']+", source)
        assert set(urls) <= {"http://www.w3.org/2000/svg"}, urls

    def test_dashboard_html_carries_the_single_worker_caveat(self):
        state = make_state(dashboard=True, dashboard_auth="token")
        source = monitor_cmd.render_monitor_files(state, dashboard=True)[
            "core/monitor_dashboard.py"
        ]
        assert "per-process" in source

    @pytest.mark.parametrize("provider", monitor_state.MONITOR_PROVIDERS)
    def test_sdk_module_renders_and_samples(self, provider):
        source = monitor_cmd.render_sdk_module(provider, "demo-api")
        ast.parse(source)
        assert "MONITOR_TRACES_SAMPLE_RATE" in source
        assert "_sample_rate()" in source

    def test_sentry_sdk_does_not_send_pii_by_default(self):
        source = monitor_cmd.render_sdk_module("sentry", "demo-api")
        assert "send_default_pii=False" in source

    def test_mongodb_project_gets_a_document_store_size_probe(self):
        source = monitor_cmd.render_monitor_files(
            make_state(db_type="mongodb"), dashboard=False
        )["core/metrics.py"]
        assert "dbStats" in source
        assert "pg_database_size" not in source

    def test_relational_project_gets_a_sql_size_probe(self):
        source = monitor_cmd.render_monitor_files(
            make_state(db_type="postgresql"), dashboard=False
        )["core/metrics.py"]
        assert "pg_database_size" in source
        assert "dbStats" not in source


# ---------------------------------------------------------------------------
# main.py wiring
# ---------------------------------------------------------------------------


@pytest.fixture()
def rendered_main() -> str:
    """The generated main.py exactly as Phase 3 writes it."""
    return (
        jinja()
        .get_template("main_app_v3.py.j2")
        .render(project_name="demo-api", db_type="sqlite", api_version="v1")
    )


class TestSpliceMain:
    def test_metrics_middleware_registers_after_security(self, rendered_main):
        spliced = monitor_cmd.splice_main(rendered_main, dashboard=False)
        assert spliced.index("register_security_middleware(app)") < spliced.index(
            "register_metrics_middleware(app)"
        )

    def test_splice_is_idempotent(self, rendered_main):
        once = monitor_cmd.splice_main(rendered_main, dashboard=False)
        twice = monitor_cmd.splice_main(once, dashboard=False)
        assert once == twice
        assert once.count("register_metrics_middleware(app)") == 1
        assert once.count(monitor_cmd._METRICS_IMPORT) == 1

    def test_splice_registers_probe_router(self, rendered_main):
        spliced = monitor_cmd.splice_main(rendered_main, dashboard=False)
        assert "app.include_router(probes_router)" in spliced
        assert "app.include_router(monitor_router)" not in spliced

    def test_dashboard_flag_registers_the_dashboard_router(self, rendered_main):
        spliced = monitor_cmd.splice_main(rendered_main, dashboard=True)
        assert "app.include_router(monitor_router)" in spliced

    def test_result_is_valid_python(self, rendered_main):
        ast.parse(monitor_cmd.splice_main(rendered_main, dashboard=True))

    def test_unknown_main_is_left_alone(self):
        hand_written = "from fastapi import FastAPI\napp = FastAPI()\n"
        assert monitor_cmd.splice_main(hand_written, dashboard=False) == hand_written

    def test_sdk_splice_is_idempotent(self, rendered_main):
        once = monitor_cmd.splice_sdk_init(rendered_main)
        assert "init_monitoring()" in once
        assert monitor_cmd.splice_sdk_init(once) == once


class TestNonDisruptive:
    """The two regressions this phase must never cause."""

    def test_health_route_and_response_are_unchanged(self, rendered_main):
        before = _health_function(rendered_main)
        after = _health_function(monitor_cmd.splice_main(rendered_main, dashboard=True))
        assert before is not None, "fixture no longer contains /health"
        assert before == after, "/health was modified by monitor init"

    def test_health_keeps_its_route_decorator(self, rendered_main):
        spliced = monitor_cmd.splice_main(rendered_main, dashboard=True)
        assert '@app.get("/health", tags=["HealthCheck"])' in spliced

    def test_health_gains_no_auth_dependency(self, rendered_main):
        after = _health_function(monitor_cmd.splice_main(rendered_main, dashboard=True))
        assert after is not None
        assert "Depends" not in after

    def test_security_middleware_is_still_registered_first(self, rendered_main):
        spliced = monitor_cmd.splice_main(rendered_main, dashboard=True)
        calls = [
            line.strip()
            for line in spliced.splitlines()
            if line.strip().endswith("(app)") and line.strip().startswith("register_")
        ]
        assert calls[0] == "register_security_middleware(app)"
        assert calls.index("register_metrics_middleware(app)") > calls.index(
            "register_security_middleware(app)"
        )

    def test_docker_healthcheck_still_targets_health(self):
        state = docker_state.ProjectState(
            project_name="demo", project_slug="demo", metrics=True
        )
        services = docker_state.build_app(state, docker_state.PROD)
        probe = " ".join(services[0]["healthcheck"]["test"])
        assert "/health" in probe
        assert "/healthz" not in probe


def _health_function(source: str) -> str | None:
    """Return the source of main.py's ``health_check`` function, if present."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "health_check":
                return ast.unparse(node)
    return None


# ---------------------------------------------------------------------------
# The generated metrics module, exercised for real
# ---------------------------------------------------------------------------


@pytest.fixture()
def generated_core(tmp_path, monkeypatch):
    """Import the rendered core/metrics.py as a real module and yield it."""
    files = monitor_cmd.render_monitor_files(make_state(), dashboard=False)
    for name in ("core", "middleware"):
        package = tmp_path / name
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
    for name, source in files.items():
        if name.startswith(("core/", "middleware/")):
            (tmp_path / name).write_text(source, encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    _unload_generated()

    import importlib

    importlib.invalidate_caches()
    import core.metrics as metrics  # type: ignore[import-not-found]

    metrics.WINDOW.reset()
    yield metrics

    _unload_generated()


def _unload_generated() -> None:
    """Drop a previously imported generated module and its Prometheus collectors.

    The generated ``core/metrics.py`` registers its counters in
    prometheus_client's default registry at import time — correct for an
    application that imports it once, fatal for a test suite that renders it into
    a fresh tmp_path per test. Unregistering first is what lets each test import
    a genuinely fresh copy instead of testing a stale one.
    """
    for stale in [
        key for key in sys.modules if key.split(".")[0] in {"core", "middleware"}
    ]:
        sys.modules.pop(stale, None)
    try:
        from prometheus_client import REGISTRY
    except ImportError:
        return
    for collector, names in list(getattr(REGISTRY, "_collector_to_names", {}).items()):
        if any(name.startswith("kaira_") for name in names):
            REGISTRY.unregister(collector)


class TestGeneratedMetrics:
    def test_percentile_is_nearest_rank(self, generated_core):
        samples = [float(n) for n in range(1, 101)]
        assert generated_core.percentile(samples, 0.50) == 50.0
        assert generated_core.percentile(samples, 0.95) == 95.0
        assert generated_core.percentile([], 0.95) == 0.0

    def test_records_traffic_and_errors(self, generated_core):
        for _ in range(9):
            generated_core.record_request("GET", "/api/v1/users", 200, 0.01, "User")
        generated_core.record_request("GET", "/api/v1/users", 500, 0.4, "User")

        totals = generated_core.WINDOW.totals()
        assert totals["requests_window"] == 10
        assert totals["errors_window"] == 1
        assert totals["error_rate"] == 0.1

    def test_model_activity_attributes_to_the_model(self, generated_core):
        generated_core.record_request("GET", "/api/v1/orders", 200, 0.01, "Order")
        generated_core.record_request("GET", "/api/v1/users", 200, 0.01, "User")
        generated_core.record_request("GET", "/api/v1/users", 500, 0.01, "User")

        rows = {row["model"]: row for row in generated_core.WINDOW.model_activity()}
        assert rows["User"]["count"] == 2
        assert rows["User"]["errors"] == 1
        assert rows["Order"]["errors"] == 0

    def test_security_feed_counts_what_the_app_already_returned(self, generated_core):
        generated_core.record_request("POST", "/api/v1/auth/login", 401, 0.01)
        generated_core.record_request("GET", "/api/v1/users", 403, 0.01)
        generated_core.record_request("GET", "/api/v1/users", 429, 0.01)

        events = generated_core.WINDOW.security_events()
        assert events["counts"] == {
            "auth_failed": 1,
            "forbidden": 1,
            "rate_limited": 1,
        }
        assert len(events["recent"]) == 3

    def test_top_routes_rank_by_traffic_and_latency(self, generated_core):
        for _ in range(5):
            generated_core.record_request("GET", "/api/v1/users", 200, 0.005)
        generated_core.record_request("GET", "/api/v1/reports", 200, 2.0)

        routes = generated_core.WINDOW.top_routes()
        assert routes["by_traffic"][0]["route"] == "GET /api/v1/users"
        assert routes["by_latency"][0]["route"] == "GET /api/v1/reports"

    def test_route_cardinality_is_capped(self, generated_core):
        limit = generated_core.MAX_ROUTES
        for index in range(limit + 25):
            generated_core.record_request("GET", f"/api/v1/thing{index}", 200, 0.01)
        tracked = generated_core.WINDOW._recent(1)[0].routes
        assert len(tracked) <= limit + 1  # +1 for the `other` bucket
        assert f"GET {generated_core.OTHER_ROUTE}" in tracked or (
            generated_core.OTHER_ROUTE in tracked
        )

    def test_anomaly_needs_a_baseline_before_it_fires(self, generated_core):
        for _ in range(20):
            generated_core.record_request("GET", "/api/v1/users", 200, 5.0)
        assert generated_core.WINDOW.anomalies() == []

    def test_anomaly_compares_a_route_against_itself(self, generated_core):
        window = generated_core.WINDOW
        route = "GET /api/v1/users"
        # Seed a completed day of history at 100ms, then run hot at 1s.
        window._baselines[route] = __import__("collections").deque(
            [("2026-08-01", 0.1)], maxlen=generated_core.BASELINE_DAYS
        )
        for _ in range(20):
            generated_core.record_request("GET", "/api/v1/users", 200, 1.0)

        flagged = window.anomalies()
        assert len(flagged) == 1
        assert flagged[0]["route"] == route
        assert flagged[0]["ratio"] >= generated_core.ANOMALY_FACTOR

    def test_a_slow_but_consistent_route_is_not_flagged(self, generated_core):
        window = generated_core.WINDOW
        route = "GET /api/v1/reports"
        window._baselines[route] = __import__("collections").deque(
            [("2026-08-01", 3.0)], maxlen=generated_core.BASELINE_DAYS
        )
        for _ in range(20):
            generated_core.record_request("GET", "/api/v1/reports", 200, 3.0)
        assert window.anomalies() == []

    def test_change_markers_read_existing_history(self, generated_core, tmp_path):
        history = tmp_path / ".kaira"
        history.mkdir(exist_ok=True)
        (history / "history.jsonl").write_text(
            json.dumps({"command": "migrate run", "timestamp": "2026-08-01T09:00:00Z"})
            + "\n"
            + json.dumps(
                {"command": "generate model", "timestamp": "2026-08-01T10:00:00Z"}
            )
            + "\n",
            encoding="utf-8",
        )
        markers = generated_core.change_markers()
        assert [marker["command"] for marker in markers] == ["migrate run"]

    def test_change_markers_are_empty_without_history(self, generated_core):
        assert generated_core.change_markers() == []

    def test_prometheus_exposition_renders(self, generated_core):
        generated_core.record_request("GET", "/api/v1/users", 200, 0.01, "User")
        body, content_type = generated_core.render_prometheus()
        assert isinstance(body, bytes)
        assert "text/plain" in content_type
        if generated_core.PROMETHEUS_AVAILABLE:
            assert b"kaira_requests_total" in body

    def test_storage_limit_is_read_from_the_environment(
        self, generated_core, monkeypatch
    ):
        monkeypatch.setenv("KAIRA_STORAGE_LIMIT_MB", "512")
        assert generated_core.storage_limit_bytes() == 512 * 1024 * 1024
        monkeypatch.setenv("KAIRA_STORAGE_LIMIT_MB", "not-a-number")
        assert generated_core.storage_limit_bytes() == 0


# ---------------------------------------------------------------------------
# The generated middleware, driven through a real FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture()
def instrumented_app(generated_core):
    """A FastAPI app wired the way `monitor init` wires a generated project."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    import middleware.metrics as metrics_middleware  # type: ignore[import-not-found]

    application = FastAPI()

    @application.middleware("http")
    async def fake_security(request, call_next):
        """Stands in for the security middleware: times the request once."""
        import time as _time

        start = _time.perf_counter()
        response = await call_next(request)
        response.headers["X-Response-Time"] = (
            f"{(_time.perf_counter() - start) * 1000:.1f}ms"
        )
        return response

    metrics_middleware.register_metrics_middleware(application)

    users = __import__("fastapi").APIRouter(prefix="/api/v1/users", tags=["User"])

    @users.get("/{uuid}")
    async def get_user(uuid: str) -> dict:
        return {"uuid": uuid}

    application.include_router(users)

    @application.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("kaboom")

    return application, TestClient(application, raise_server_exceptions=False)


class TestGeneratedMiddleware:
    def test_labels_use_the_route_template_not_the_real_id(
        self, generated_core, instrumented_app
    ):
        _, client = instrumented_app
        client.get("/api/v1/users/11111111-2222-3333-4444-555555555555")
        client.get("/api/v1/users/99999999-8888-7777-6666-555555555555")

        routes = list(generated_core.iter_route_names())
        assert routes == ["GET /api/v1/users/{uuid}"], routes

    def test_unmatched_paths_do_not_inflate_cardinality(
        self, generated_core, instrumented_app
    ):
        _, client = instrumented_app
        for index in range(20):
            client.get(f"/nope/{index}")
        routes = list(generated_core.iter_route_names())
        assert len(routes) == 1

    def test_model_is_resolved_from_the_router_tag(
        self, generated_core, instrumented_app
    ):
        _, client = instrumented_app
        client.get("/api/v1/users/abc")
        rows = {row["model"] for row in generated_core.WINDOW.model_activity()}
        assert rows == {"User"}

    def test_a_crashed_request_is_still_counted(self, generated_core, instrumented_app):
        _, client = instrumented_app
        client.get("/boom")
        totals = generated_core.WINDOW.totals()
        assert totals["requests_window"] == 1
        assert totals["errors_window"] == 1

    def test_duration_comes_from_the_response_header(self, generated_core):
        import middleware.metrics as metrics_middleware  # type: ignore[import-not-found]

        class FakeResponse:
            headers = {"X-Response-Time": "250.0ms"}

        seconds = metrics_middleware._duration_seconds(FakeResponse(), 0.0)
        assert abs(seconds - 0.25) < 1e-9

    def test_normalise_path_collapses_identifiers(self, generated_core):
        import middleware.metrics as metrics_middleware  # type: ignore[import-not-found]

        assert metrics_middleware.normalise_path("/users/42") == "/users/{id}"
        assert (
            metrics_middleware.normalise_path(
                "/users/11111111-2222-3333-4444-555555555555"
            )
            == "/users/{id}"
        )
        assert metrics_middleware.normalise_path("/users/list") == "/users/list"


# ---------------------------------------------------------------------------
# Logger — JSON mode is a formatter, never a file
# ---------------------------------------------------------------------------


class TestJsonLogMode:
    @pytest.fixture()
    def logger_source(self) -> str:
        return jinja().get_template("logger.py.j2").render(project_name="demo-api")

    def test_json_mode_is_opt_in(self, logger_source):
        assert 'os.getenv("KAIRA_LOG_FORMAT", "text")' in logger_source

    def test_the_default_path_is_unchanged(self, logger_source):
        assert "format=_formatter" in logger_source
        assert "colorize=_COLOR" in logger_source

    def test_there_is_no_file_sink(self, logger_source):
        tree = ast.parse(logger_source)
        sinks = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add"
        ]
        assert sinks, "logger.add disappeared"
        for sink in sinks:
            first = ast.unparse(sink.args[0]) if sink.args else ""
            assert first in {"sys.stdout", "_json_sink"}, (
                f"logger.add({first}) is not a stdout sink"
            )
        assert "rotation=" not in logger_source
        assert "retention=" not in logger_source

    def test_structured_mode_never_enables_diagnose(self, logger_source):
        block = logger_source.split("if JSON_LOGS:")[1].split("else:")[0]
        assert "diagnose=False" in block

    def test_json_line_is_parseable(self, logger_source):
        namespace: dict = {}
        # Exec only the pure helper, without loguru's import at module scope.
        tree = ast.parse(logger_source)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_json_line":
                exec(  # nosec B102 - executing a function we just generated
                    compile(
                        ast.Module(body=[node], type_ignores=[]), "<logger>", "exec"
                    ),
                    {"json": json, "_JSON_RESERVED": {"kaira_http", "show_id"}},
                    namespace,
                )
        assert "_json_line" in namespace

        class Level:
            name = "INFO"

        record = {
            "time": datetime(2026, 8, 14, tzinfo=timezone.utc),
            "level": Level(),
            "message": "hello",
            "name": "app",
            "extra": {
                "kaira_http": True,
                "method": "GET",
                "path": "/api/v1/users",
                "status": 200,
                "duration_ms": 12.345,
                "request_id": "abc",
                "client": "127.0.0.1",
                "show_id": False,
            },
            "exception": None,
        }
        payload = json.loads(namespace["_json_line"](record))
        assert payload["status"] == 200
        assert payload["duration_ms"] == 12.35
        assert payload["event"] == "request"
        # Presentation-only keys are not facts about the event.
        assert "kaira_http" not in payload and "show_id" not in payload


# ---------------------------------------------------------------------------
# Prometheus text parsing (the watch/status fallback)
# ---------------------------------------------------------------------------


class TestPrometheusParsing:
    SAMPLE = """
# HELP kaira_requests_total Total requests
# TYPE kaira_requests_total counter
kaira_requests_total{method="GET",path="/api/v1/users",status="200"} 90.0
kaira_requests_total{method="GET",path="/api/v1/users",status="500"} 10.0
kaira_errors_total{method="GET",path="/api/v1/users",status="500"} 10.0
kaira_request_duration_seconds_bucket{le="0.1",method="GET",path="/x"} 80.0
kaira_request_duration_seconds_bucket{le="0.5",method="GET",path="/x"} 99.0
kaira_request_duration_seconds_bucket{le="+Inf",method="GET",path="/x"} 100.0
kaira_request_duration_seconds_count{method="GET",path="/x"} 100.0
"""

    def test_totals_and_error_rate(self):
        payload = monitor_cmd.parse_prometheus(self.SAMPLE)
        assert payload["totals"]["requests_total"] == 100
        assert payload["totals"]["errors_total"] == 10
        assert payload["totals"]["error_rate"] == 0.1

    def test_p95_from_histogram_buckets(self):
        payload = monitor_cmd.parse_prometheus(self.SAMPLE)
        assert payload["latency"]["p95_ms"] == 500.0

    def test_empty_input_is_safe(self):
        payload = monitor_cmd.parse_prometheus("")
        assert payload["totals"]["error_rate"] == 0.0


# ---------------------------------------------------------------------------
# Thresholds and diffing
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_no_breach_when_within_bounds(self):
        payload = {"totals": {"error_rate": 0.01}, "latency": {"p95_ms": 100}}
        assert (
            monitor_cmd.evaluate_thresholds(payload, error_rate=0.05, p95_ms=500) == []
        )

    def test_error_rate_breach(self):
        payload = {"totals": {"error_rate": 0.2}, "latency": {"p95_ms": 10}}
        breaches = monitor_cmd.evaluate_thresholds(payload, error_rate=0.05, p95_ms=500)
        assert len(breaches) == 1 and "error rate" in breaches[0]

    def test_latency_breach(self):
        payload = {"totals": {"error_rate": 0.0}, "latency": {"p95_ms": 900}}
        breaches = monitor_cmd.evaluate_thresholds(payload, error_rate=0.05, p95_ms=500)
        assert len(breaches) == 1 and "p95" in breaches[0]

    def test_anomalies_are_surfaced_as_breaches(self):
        payload = {
            "totals": {"error_rate": 0.0},
            "latency": {"p95_ms": 10},
            "anomalies": [{"route": "GET /x", "ratio": 3.1}],
        }
        breaches = monitor_cmd.evaluate_thresholds(payload, error_rate=0.05, p95_ms=500)
        assert breaches == ["GET /x running 3.1× its own baseline"]


class TestDiff:
    BEFORE = {
        "totals": {"requests_window": 100, "errors_window": 1, "error_rate": 0.01},
        "latency": {"p50_ms": 10, "p95_ms": 50, "p99_ms": 90},
    }
    AFTER = {
        "totals": {"requests_window": 200, "errors_window": 20, "error_rate": 0.1},
        "latency": {"p50_ms": 10, "p95_ms": 400, "p99_ms": 900},
    }

    def test_direction_is_reported_per_metric(self):
        rows = {
            label: direction
            for label, _, _, direction in monitor_cmd.diff_payloads(
                self.BEFORE, self.AFTER
            )
        }
        assert rows["requests"] == "up"
        assert rows["errors"] == "up"
        assert rows["p50"] == "flat"
        assert rows["p95"] == "up"

    def test_identical_snapshots_are_all_flat(self):
        rows = monitor_cmd.diff_payloads(self.BEFORE, self.BEFORE)
        assert {direction for *_, direction in rows} == {"flat"}

    def test_more_requests_is_not_worse_but_more_errors_is(self):
        # The row labels drive the good/bad colouring in the command.
        assert "requests" not in monitor_cmd._WORSE_WHEN_UP
        assert "errors" in monitor_cmd._WORSE_WHEN_UP
        assert "p95" in monitor_cmd._WORSE_WHEN_UP


# ---------------------------------------------------------------------------
# Docker integration — through the existing dynamic rendering
# ---------------------------------------------------------------------------


class TestDockerIntegration:
    def test_metrics_appears_in_enabled_features(self):
        state = docker_state.ProjectState(
            project_name="demo", project_slug="demo", metrics=True
        )
        assert "metrics (/metrics)" in docker_state.enabled_features(state)

    def test_metrics_adds_no_compose_service(self):
        without = docker_state.build_services(
            docker_state.ProjectState(project_name="d", project_slug="d"), "dev"
        )
        with_metrics = docker_state.build_services(
            docker_state.ProjectState(project_name="d", project_slug="d", metrics=True),
            "dev",
        )
        assert [svc["name"] for svc in without] == [svc["name"] for svc in with_metrics]

    def test_compose_header_records_metrics(self):
        state = docker_state.ProjectState(
            project_name="demo", project_slug="demo", metrics=True
        )
        from kaira.core import docker_render

        rendered = docker_render.render_files(state, with_compose=True)
        assert "metrics: /metrics" in rendered["docker-compose.yml"]

    def test_compose_is_unchanged_without_metrics(self):
        state = docker_state.ProjectState(project_name="demo", project_slug="demo")
        from kaira.core import docker_render

        rendered = docker_render.render_files(state, with_compose=True)
        assert "metrics: /metrics" not in rendered["docker-compose.yml"]

    def test_detect_metrics_is_separate_from_provider_detection(self, tmp_path):
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "metrics.py").write_text("", encoding="utf-8")
        assert docker_state.detect_metrics(tmp_path) is True
        assert docker_state.detect_monitor(tmp_path) == ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_monitor_group_is_registered(self):
        result = run("monitor", "--help")
        assert result.exit_code == 0
        for command in ("init", "status", "watch", "diff"):
            assert command in result.output

    def test_guide_monitor_documents_the_single_worker_scope(self):
        result = run("guide", "monitor")
        assert result.exit_code == 0
        assert "per-process" in result.output

    def test_guide_index_lists_monitor(self):
        result = run("guide")
        assert result.exit_code == 0
        assert "kaira guide monitor" in result.output

    def test_init_outside_a_project_exits_cleanly(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = run("monitor", "init", "--quiet")
        assert result.exit_code == 1
        assert "kaira init" in result.output

    def test_init_scaffolds_and_wires(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)

        result = run("monitor", "init", "--quiet")
        assert result.exit_code == 0, result.output

        assert (tmp_path / "core" / "metrics.py").is_file()
        assert (tmp_path / "middleware" / "metrics.py").is_file()
        assert (tmp_path / "routers" / "probes_router.py").is_file()
        assert not (tmp_path / "routers" / "monitor_router.py").exists()

        main_source = (tmp_path / "main.py").read_text(encoding="utf-8")
        assert main_source.index(
            "register_security_middleware(app)"
        ) < main_source.index("register_metrics_middleware(app)")
        assert "prometheus-client" in (tmp_path / "requirements.txt").read_text(
            encoding="utf-8"
        )

        config = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))
        assert config["monitor_metrics"] is True
        assert config["monitor_dashboard"] is False

    def test_init_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        run("monitor", "init", "--quiet")
        first = (tmp_path / "main.py").read_text(encoding="utf-8")
        run("monitor", "init", "--quiet")
        assert (tmp_path / "main.py").read_text(encoding="utf-8") == first

    def test_init_leaves_health_alone(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        before = _health_function((tmp_path / "main.py").read_text(encoding="utf-8"))
        run("monitor", "init", "--quiet")
        after = _health_function((tmp_path / "main.py").read_text(encoding="utf-8"))
        assert before is not None and before == after

    def test_dashboard_requires_an_auth_strategy_when_quiet(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        result = run("monitor", "init", "--dashboard", "--quiet")
        assert result.exit_code == 1
        assert "--auth" in result.output
        assert not (tmp_path / "routers" / "monitor_router.py").exists()

    def test_dashboard_with_token_writes_env_keys_and_stays_off(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KAIRA_MONITOR_TOKEN", raising=False)
        scaffold_project(tmp_path)

        result = run("monitor", "init", "--dashboard", "--auth", "token", "--quiet")
        assert result.exit_code == 0, result.output
        assert (tmp_path / "routers" / "monitor_router.py").is_file()

        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "KAIRA_MONITOR_ENABLED=false" in env, "the dashboard must ship off"
        token_line = [
            line for line in env.splitlines() if line.startswith("KAIRA_MONITOR_TOKEN=")
        ]
        assert token_line and len(token_line[0].split("=", 1)[1]) >= 24

        # The token is a credential: it goes to .env, never to the terminal.
        assert token_line[0].split("=", 1)[1] not in result.output

    def test_reuse_auth_is_refused_without_a_guard(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        result = run("monitor", "init", "--dashboard", "--auth", "reuse", "--quiet")
        assert result.exit_code == 1
        assert "auth/dependencies.py" in result.output

    def test_unknown_auth_strategy_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        result = run("monitor", "init", "--dashboard", "--auth", "public", "--quiet")
        assert result.exit_code == 1
        assert "public" in result.output

    def test_status_reports_an_unscaffolded_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        result = run("monitor", "status")
        assert result.exit_code == 0
        assert "kaira monitor init" in result.output

    def test_status_reports_a_scaffolded_project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        run("monitor", "init", "--quiet")
        result = run("monitor", "status")
        assert result.exit_code == 0
        assert "/metrics" in result.output
        assert "/healthz" in result.output

    def test_plain_text_symbols_survive_rich_markup(self, tmp_path, monkeypatch):
        # sym() degrades to "[ok]"/"[x]" off a TTY — which Rich would otherwise
        # parse as a style tag and swallow, leaving a blank status column.
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        run("monitor", "init", "--quiet")
        result = run("monitor", "status")
        assert "[ok]" in result.output

    def test_diff_without_snapshots_says_how_to_get_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        result = run("monitor", "diff")
        assert result.exit_code == 0
        assert "kaira monitor status" in result.output

    def test_diff_compares_two_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        directory = tmp_path / ".kaira" / "monitor"
        directory.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        for offset, payload in (
            (48, TestDiff.BEFORE),
            (0, TestDiff.AFTER),
        ):
            stamp = (now - timedelta(hours=offset)).strftime("%Y%m%dT%H%M%SZ")
            (directory / f"{stamp}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

        result = run("monitor", "diff", "--since", "yesterday")
        assert result.exit_code == 0, result.output
        assert "p95" in result.output
        assert "error rate" in result.output

    def test_watch_once_against_a_dead_app_does_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        result = run("monitor", "watch", "--once", "--url", "http://127.0.0.1:59999")
        assert result.exit_code == 0
        assert "unreachable" in result.output

    def test_watch_masks_the_webhook_url(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        secret = "https://hooks.slack.com/services/T000/B000/SUPERSECRETVALUE"
        monkeypatch.setenv("KAIRA_MONITOR_WEBHOOK_URL", secret)
        result = run("monitor", "watch", "--once", "--url", "http://127.0.0.1:59999")
        assert "SUPERSECRETVALUE" not in result.output
        assert "hooks.slack.com/***" in result.output


# ---------------------------------------------------------------------------
# Third-party SDK wiring (the `integrate monitor` completion)
# ---------------------------------------------------------------------------


class TestProviderSdkWiring:
    def test_wire_generates_the_module_and_starts_it(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)

        monitor_cmd.wire_provider_sdk(tmp_path, "sentry", quiet=True)

        sdk = tmp_path / "core" / "monitor_sdk.py"
        assert sdk.is_file()
        ast.parse(sdk.read_text(encoding="utf-8"))

        main_source = (tmp_path / "main.py").read_text(encoding="utf-8")
        assert "init_monitoring()" in main_source
        # It must start inside the lifespan, not at import time.
        assert main_source.index("async def lifespan") < main_source.index(
            "init_monitoring()"
        )
        ast.parse(main_source)

    def test_wire_records_a_sampled_rate_in_settings(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        monitor_cmd.wire_provider_sdk(tmp_path, "sentry", quiet=True)

        settings = (tmp_path / "config" / "settings.py").read_text(encoding="utf-8")
        assert "MONITOR_TRACES_SAMPLE_RATE: float = 0.2" in settings
        assert "1.0" not in settings.split("MONITOR_TRACES_SAMPLE_RATE")[1][:40]

    def test_wire_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        monitor_cmd.wire_provider_sdk(tmp_path, "sentry", quiet=True)
        first = (tmp_path / "main.py").read_text(encoding="utf-8")
        monitor_cmd.wire_provider_sdk(tmp_path, "sentry", quiet=True)
        assert (tmp_path / "main.py").read_text(encoding="utf-8") == first

    def test_unknown_provider_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        monitor_cmd.wire_provider_sdk(tmp_path, "pingdom", quiet=True)
        assert not (tmp_path / "core" / "monitor_sdk.py").exists()

    def test_tier1_never_requires_a_provider(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        run("monitor", "init", "--quiet")
        assert not (tmp_path / "core" / "monitor_sdk.py").exists()


# ---------------------------------------------------------------------------
# Alert delivery
# ---------------------------------------------------------------------------


class TestAlertDelivery:
    def test_desktop_notification_uses_the_platform_notifier(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(monitor_cmd.platform, "system", lambda: "Linux")
        monkeypatch.setattr(
            monitor_cmd.shutil, "which", lambda _: "/usr/bin/notify-send"
        )
        monkeypatch.setattr(
            monitor_cmd.subprocess,
            "run",
            lambda args, **kwargs: calls.append(args),
        )
        assert monitor_cmd.notify_desktop("Kaira", "error rate 12%") is True
        assert calls and calls[0][0] == "notify-send"

    def test_no_notifier_reports_honestly(self, monkeypatch):
        monkeypatch.setattr(monitor_cmd.platform, "system", lambda: "Linux")
        monkeypatch.setattr(monitor_cmd.shutil, "which", lambda _: None)
        assert monitor_cmd.notify_desktop("Kaira", "boom") is False

    def test_webhook_posts_a_body_both_slack_and_discord_understand(self, monkeypatch):
        sent: dict = {}

        class FakeResponse:
            status_code = 204

        class FakeClient:
            def __init__(self, **_):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def post(self, url, json=None):
                sent["url"] = url
                sent["json"] = json
                return FakeResponse()

        import httpx

        monkeypatch.setattr(httpx, "Client", FakeClient)
        assert monitor_cmd.post_webhook("https://example.com/hook", "T", "B") is True
        assert "content" in sent["json"] and "text" in sent["json"]

    def test_empty_webhook_is_a_no_op(self):
        assert monitor_cmd.post_webhook("", "T", "B") is False

    def test_webhook_failure_is_not_fatal(self, monkeypatch):
        import httpx

        def explode(**_):
            raise RuntimeError("network down")

        monkeypatch.setattr(httpx, "Client", explode)
        assert monitor_cmd.post_webhook("https://example.com/hook", "T", "B") is False


# ---------------------------------------------------------------------------
# Live paths, driven with a stubbed application
# ---------------------------------------------------------------------------


BREACHING_PAYLOAD = {
    "source": "dashboard",
    "totals": {"requests_window": 100, "errors_window": 30, "error_rate": 0.3},
    "latency": {"p50_ms": 10, "p95_ms": 1500, "p99_ms": 2000},
    "scope": {"process_id": 4242, "window_minutes": 60},
    "markers": [{"command": "migrate run", "at": "2026-08-14T09:00:00Z"}],
    "routes": {"by_latency": [{"route": "GET /api/v1/users", "p95_ms": 1500}]},
}

CALM_PAYLOAD = {
    "source": "dashboard",
    "totals": {"requests_window": 100, "errors_window": 0, "error_rate": 0.0},
    "latency": {"p50_ms": 5, "p95_ms": 20, "p99_ms": 40},
    "scope": {"process_id": 4242, "window_minutes": 60},
}


class TestLivePaths:
    def test_status_renders_live_numbers_and_saves_a_snapshot(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        run("monitor", "init", "--quiet")
        monkeypatch.setattr(
            monitor_cmd, "fetch_live_payload", lambda *a, **k: CALM_PAYLOAD
        )

        result = run("monitor", "status")
        assert result.exit_code == 0, result.output
        assert "0.00%" in result.output
        assert "pid 4242" in result.output
        assert monitor_state.list_snapshots(tmp_path)

    def test_status_states_the_single_worker_caveat(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        run("monitor", "init", "--quiet")
        monkeypatch.setattr(
            monitor_cmd, "fetch_live_payload", lambda *a, **k: CALM_PAYLOAD
        )
        result = run("monitor", "status")
        # Rich soft-wraps the caveat, so compare on collapsed whitespace.
        assert "not an aggregate" in " ".join(result.output.split())

    def test_watch_alerts_once_per_transition(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        alerts: list[str] = []
        monkeypatch.setattr(
            monitor_cmd, "fetch_live_payload", lambda *a, **k: BREACHING_PAYLOAD
        )
        monkeypatch.setattr(
            monitor_cmd,
            "notify_desktop",
            lambda title, message: alerts.append(message) or True,
        )

        result = run("monitor", "watch", "--once")
        assert result.exit_code == 0, result.output
        assert len(alerts) == 1
        assert "error rate" in alerts[0]

    def test_watch_is_quiet_when_everything_is_fine(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        alerts: list[str] = []
        monkeypatch.setattr(
            monitor_cmd, "fetch_live_payload", lambda *a, **k: CALM_PAYLOAD
        )
        monkeypatch.setattr(
            monitor_cmd,
            "notify_desktop",
            lambda title, message: alerts.append(message) or True,
        )
        run("monitor", "watch", "--once")
        assert alerts == []

    def test_fetch_falls_back_to_metrics_when_the_dashboard_is_off(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)

        class FakeResponse:
            status_code = 200
            text = TestPrometheusParsing.SAMPLE

        class FakeClient:
            def __init__(self, **_):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def get(self, url, headers=None):
                if "/_kaira/" in url:
                    raise RuntimeError("dashboard disabled")
                return FakeResponse()

        import httpx

        monkeypatch.setattr(httpx, "Client", FakeClient)
        payload = monitor_cmd.fetch_live_payload()
        assert payload is not None
        assert payload["source"] == "prometheus"
        assert payload["totals"]["error_rate"] == 0.1

    def test_fetch_returns_none_when_nothing_answers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        assert monitor_cmd.fetch_live_payload("http://127.0.0.1:59998", 0.2) is None

    def test_diff_reports_route_and_marker_changes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        write_project(tmp_path)
        directory = tmp_path / ".kaira" / "monitor"
        directory.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        older = {
            "totals": {"requests_window": 10, "errors_window": 0, "error_rate": 0.0},
            "latency": {"p50_ms": 5, "p95_ms": 20, "p99_ms": 30},
            "routes": {"by_latency": [{"route": "GET /api/v1/users", "p95_ms": 20}]},
            "markers": [],
        }
        for offset, payload in ((48, older), (0, BREACHING_PAYLOAD)):
            stamp = (now - timedelta(hours=offset)).strftime("%Y%m%dT%H%M%SZ")
            (directory / f"{stamp}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

        result = run("monitor", "diff", "--since", "yesterday")
        assert result.exit_code == 0, result.output
        assert "GET /api/v1/users" in result.output
        assert "migrate run" in result.output


# ---------------------------------------------------------------------------
# Dashboard with the project's own auth guard
# ---------------------------------------------------------------------------


class TestDashboardReuseAuth:
    def test_reuse_wires_the_projects_guard(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        (tmp_path / "auth").mkdir()
        (tmp_path / "auth" / "dependencies.py").write_text(
            "def get_current_user():\n    return {}\n", encoding="utf-8"
        )

        result = run("monitor", "init", "--dashboard", "--auth", "reuse", "--quiet")
        assert result.exit_code == 0, result.output

        router = (tmp_path / "routers" / "monitor_router.py").read_text(
            encoding="utf-8"
        )
        assert "from auth.dependencies import get_current_user" in router
        assert "Depends(get_current_user)" in router

        config = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))
        assert config["monitor_dashboard_auth"] == "reuse"

    def test_no_token_is_written_for_the_reuse_strategy(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        scaffold_project(tmp_path)
        (tmp_path / "auth").mkdir()
        (tmp_path / "auth" / "dependencies.py").write_text("", encoding="utf-8")
        run("monitor", "init", "--dashboard", "--auth", "reuse", "--quiet")
        env = (tmp_path / ".env").read_text(encoding="utf-8")
        assert "KAIRA_MONITOR_ENABLED=false" in env
        assert "KAIRA_MONITOR_TOKEN" not in env
