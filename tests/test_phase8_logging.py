"""Phase 8 — runtime display & error handling for the generated app.

Two layers of coverage:

* Template contract tests — cheap assertions that the generated source keeps the
  properties the redesign depends on (levels, exported helpers, no deprecated
  constants).
* Behavioural tests — render the templates into a throwaway project and run it
  in a subprocess, asserting on the terminal output and the HTTP error bodies
  that a developer actually sees.

The subprocess is deliberate: ``core/logger.py`` reconfigures the global loguru
sink and the stdlib root logger at import time, which would leak into the rest
of the suite if imported in-process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).parent.parent / "kaira" / "templates"


def _template(name: str) -> str:
    """Return raw template source."""
    return (TEMPLATES / name).read_text(encoding="utf-8")


# ── Template contract ────────────────────────────────────────────────────────


def test_logger_exposes_the_display_helpers():
    """The middleware and main.py import these by name — they are the contract."""
    source = _template("logger.py.j2")

    assert "def detail(" in source
    assert "def http(" in source
    assert "def is_debug(" in source
    assert "def status_style(" in source
    # A callable formatter is what keeps user-supplied paths out of the colour
    # markup parser; a static format string would reintroduce that risk.
    assert "format=_formatter" in source


def test_logger_silences_duplicate_request_and_lifecycle_noise():
    """One line per request: uvicorn's access log and boot chatter stand down."""
    source = _template("logger.py.j2")

    assert 'logging.getLogger("uvicorn.access").setLevel(logging.WARNING)' in source
    assert "KAIRA_ACCESS_LOG" in source
    for demoted in ("Started server process", "Application startup complete"):
        assert demoted in source
    # Uvicorn re-logs handled exceptions; the second traceback is pure noise.
    assert "Exception in ASGI application" in source
    for chatty in ("watchfiles", "httpx", "pymongo"):
        assert chatty in source


def test_router_entry_traces_are_debug_only():
    """The request line already reports method, path and status."""
    source = _template("router.py.j2")

    assert "logger.info(" not in source
    assert source.count("logger.debug(") >= 8


def test_service_keeps_mutations_visible_and_reads_quiet():
    """Reads collapse into the request line; state changes stay on screen."""
    source = _template("service.py.j2")

    assert "logger.info(" not in source
    for mutation in ("created ·", "updated ·", "deleted ·"):
        assert mutation in source
    # Read paths must not emit SUCCESS — that is what made every GET two lines.
    assert "logger.success" in source
    assert "returned {len(objects)} records" not in source


def test_middleware_error_contract():
    """Every failure returns the same envelope and a traceable request id."""
    source = _template("security_middleware.py.j2")

    for handler in (
        "RequestValidationError",
        "RateLimitExceeded",
        "StarletteHTTPException",
        "@app.exception_handler(Exception)",
    ):
        assert handler in source

    assert "request.state.request_id = request_id" in source
    assert '"X-Request-ID"' in source
    # starlette deprecated the old 422 constant and warns on every use of it.
    assert "status.HTTP_422_UNPROCESSABLE_ENTITY" not in source
    # Library frames are filtered out of reported tracebacks.
    assert "site-packages" in source


# ── Behavioural harness ──────────────────────────────────────────────────────

APP_SOURCE = """\
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from middleware.security import (
    register_exception_handlers,
    register_security_middleware,
)
from rate_limit import limiter

app = FastAPI(title="probe")
app.state.limiter = limiter
register_security_middleware(app)
register_exception_handlers(app)


class UserIn(BaseModel):
    email: str
    age: int


@app.get("/users/list")
def list_users():
    return [{"id": 1}]


@app.get("/users/{uuid}")
def get_user(uuid: str):
    raise HTTPException(status_code=404, detail="User not found.")


@app.post("/users")
def create_user(data: UserIn):
    return data


@app.get("/boom")
def boom():
    from domain import load_user

    return load_user("abc")
"""

DOMAIN_SOURCE = """\
def parse_age(raw: str) -> int:
    return int(raw)


def load_user(uuid: str) -> dict:
    return {"uuid": uuid, "age": parse_age("not-a-number")}
"""

SETTINGS_SOURCE = """\
class _Settings:
    APP_ENV = "development"
    ALLOWED_ORIGINS = ["*"]


settings = _Settings()
"""

RATE_LIMIT_SOURCE = """\
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
"""

PROBE_SOURCE = """\
import json

from fastapi.testclient import TestClient

from app import app

client = TestClient(app, raise_server_exceptions=False)
results = {}

ok = client.get("/users/list")
results["ok"] = {"status": ok.status_code, "request_id": ok.headers.get("x-request-id")}

missing = client.get("/users/nope")
results["missing"] = {"status": missing.status_code, "body": missing.json()}

invalid = client.post("/users", json={"email": 5})
results["invalid"] = {"status": invalid.status_code, "body": invalid.json()}

crashed = client.get("/boom")
results["crashed"] = {
    "status": crashed.status_code,
    "body": crashed.json(),
    "request_id": crashed.headers.get("x-request-id"),
}

with open("results.json", "w", encoding="utf-8") as handle:
    json.dump(results, handle)

from core.logger import logger

logger.complete()
"""


def _build_project(root: Path) -> None:
    """Render the real templates into a minimal runnable project."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)), keep_trailing_newline=True
    )
    context = {
        "project_name": "probe",
        "project_slug": "probe",
        "db_type": "mongodb",
        "auth_type": "none",
        "api_version": "v1",
    }

    for package in ("core", "middleware", "config"):
        (root / package).mkdir(parents=True, exist_ok=True)
        (root / package / "__init__.py").write_text("", encoding="utf-8")

    (root / "core" / "logger.py").write_text(
        env.get_template("logger.py.j2").render(**context), encoding="utf-8"
    )
    (root / "middleware" / "security.py").write_text(
        env.get_template("security_middleware.py.j2").render(**context),
        encoding="utf-8",
    )
    (root / "config" / "settings.py").write_text(SETTINGS_SOURCE, encoding="utf-8")
    (root / "rate_limit.py").write_text(RATE_LIMIT_SOURCE, encoding="utf-8")
    (root / "app.py").write_text(APP_SOURCE, encoding="utf-8")
    (root / "domain.py").write_text(DOMAIN_SOURCE, encoding="utf-8")


def _run(root: Path, source: str, **env_overrides: str) -> str:
    """Execute *source* inside the generated project, returning its stdout."""
    script = root / "_probe.py"
    script.write_text(source, encoding="utf-8")

    env = dict(os.environ)
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "NO_COLOR": "1",
            "APP_ENV": "development",
        }
    )
    env.update(env_overrides)

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """Render the project once, run it, and share the output across assertions."""
    pytest.importorskip("fastapi")
    pytest.importorskip("slowapi")
    pytest.importorskip("loguru")

    root = tmp_path_factory.mktemp("probe")
    _build_project(root)
    output = _run(root, PROBE_SOURCE)
    results = json.loads((root / "results.json").read_text(encoding="utf-8"))
    return output, results


# ── Behaviour: the display ───────────────────────────────────────────────────


def test_a_successful_request_is_exactly_one_line(probe):
    """The old pipeline printed five lines for one GET."""
    output, _ = probe
    lines = [line for line in output.splitlines() if "/users/list" in line]

    assert len(lines) == 1
    assert "INFO" in lines[0]
    assert "GET" in lines[0]
    assert "200" in lines[0]
    assert "ms" in lines[0]


def test_status_class_drives_the_level(probe):
    """Colour follows severity because the level does — 4xx warns, 5xx errors."""
    output, _ = probe

    missing = next(line for line in output.splitlines() if "404" in line)
    crashed = next(
        line for line in output.splitlines() if "500" in line and "/boom" in line
    )

    assert "WARNING" in missing
    assert "ERROR" in crashed
    # A failed request shows its correlation id; a healthy one does not.
    assert "req " in missing
    healthy = next(line for line in output.splitlines() if "/users/list" in line)
    assert "req " not in healthy


def test_validation_failure_lists_the_offending_fields(probe):
    """Instead of a raw pydantic dump, one aligned block naming each field."""
    output, _ = probe
    block = output.split("rejected")[1]

    assert "2 invalid field(s)" in block
    assert "body.email" in block
    assert "body.age" in block


def test_crash_block_shows_only_application_frames(probe):
    """The traceback names the developer's code, not starlette's plumbing."""
    output, _ = probe
    block = output.split("Unhandled ValueError")[1].split("500")[0]

    assert "traceback (innermost last)" in block
    assert "domain.py:2 in parse_age" in block
    assert "app.py" in block
    # Framework frames are what made the old traceback unreadable.
    assert "site-packages" not in block
    assert "starlette" not in block
    # The middleware's own call_next frame is plumbing too.
    assert "security.py" not in block


def test_detail_blocks_align_under_the_message_column(probe):
    """Continuation lines are indented to the message column, not column zero."""
    output, _ = probe
    continuations = [
        line
        for line in output.splitlines()
        if line.startswith("  ") and ("├─" in line or "└─" in line)
    ]

    assert continuations
    assert all(line.startswith(" " * 20) for line in continuations)


# ── Behaviour: the error contract ────────────────────────────────────────────


def test_every_error_returns_the_same_envelope(probe):
    """Validation, HTTP and crash responses share one shape."""
    _, results = probe

    for key, status_code, code in (
        ("missing", 404, "http_error"),
        ("invalid", 422, "validation_error"),
        ("crashed", 500, "internal_error"),
    ):
        body = results[key]["body"]
        assert results[key]["status"] == status_code
        assert body["error"]["code"] == code
        assert body["error"]["status"] == status_code
        assert body["error"]["request_id"]
        assert body["error"]["path"]
        # `detail` is preserved so existing clients keep working.
        assert "detail" in body


def test_validation_response_carries_structured_fields(probe):
    """The 422 body names each field, while `detail` keeps pydantic's list."""
    _, results = probe
    body = results["invalid"]["body"]

    fields = {row["field"]: row["message"] for row in body["error"]["fields"]}
    assert "body.email" in fields
    assert "body.age" in fields
    assert isinstance(body["detail"], list)


def test_crash_response_is_traceable_but_not_leaky(probe):
    """The id in the body matches the header — and the log line above it."""
    output, results = probe
    crashed = results["crashed"]

    assert crashed["body"]["error"]["request_id"] == crashed["request_id"]
    assert crashed["request_id"] in output
    assert "An internal error occurred" in crashed["body"]["detail"]
    # No traceback, no file paths, no frames in the response body.
    assert "Traceback" not in json.dumps(crashed["body"])
    assert "domain.py" not in json.dumps(crashed["body"])


def test_every_response_carries_a_request_id_header(probe):
    """Correlation works for successes too, not just failures."""
    _, results = probe

    assert results["ok"]["status"] == 200
    assert results["ok"]["request_id"]


# ── Behaviour: the startup / shutdown surfaces of `kaira run` ────────────────


class _Completed:
    """Stand-in for the server process so no server is actually started."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    """Run `kaira run` against a stub project, capturing the child environment."""
    from kaira.commands import run_cmd

    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.py").write_text("app = None\n", encoding="utf-8")

    captured: dict = {}

    def _factory(returncode: int = 0):
        def fake_run(cmd, cwd=None, env=None, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = env
            return _Completed(returncode)

        monkeypatch.setattr(run_cmd.subprocess, "run", fake_run)
        return captured

    return _factory


def test_run_debug_flag_raises_the_child_log_level(fake_server):
    """--debug is the single switch for per-layer traces and full tracebacks."""
    from typer.testing import CliRunner

    from kaira.main import app as kaira_app

    captured = fake_server()
    result = CliRunner().invoke(kaira_app, ["run", "--debug"])

    assert result.exit_code == 0
    assert captured["env"]["KAIRA_LOG_LEVEL"] == "DEBUG"
    assert "KAIRA_ACCESS_LOG" not in captured["env"]


def test_run_defaults_to_quiet_child_environment(fake_server):
    """Without flags the app keeps its one-line-per-request default."""
    from typer.testing import CliRunner

    from kaira.main import app as kaira_app

    captured = fake_server()
    result = CliRunner().invoke(kaira_app, ["run", "--access-log"])

    assert result.exit_code == 0
    assert "KAIRA_LOG_LEVEL" not in captured["env"]
    assert captured["env"]["KAIRA_ACCESS_LOG"] == "1"


def test_run_explains_a_non_zero_exit(fake_server):
    """A crashed server used to print the same neutral 'Server stopped.' panel."""
    from typer.testing import CliRunner

    from kaira.main import app as kaira_app

    fake_server(returncode=3)
    result = CliRunner().invoke(kaira_app, ["run"])

    assert result.exit_code == 3
    assert "exited with code 3" in result.output
    assert "Port in use" in result.output
    assert "Server stopped." not in result.output
