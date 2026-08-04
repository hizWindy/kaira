"""Phase 6 tests — auto DB provisioning, offline/online Layer 1, run/mode reporting.

Covers the security-critical guarantees called out in the Phase 6 deliverables:
credentials are never printed, the identifier allowlist rejects injection,
offline-mode resolution is correct, and mode is reported consistently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kaira.core import provisioner as p


# ---------------------------------------------------------------------------
# Name sanitization + identifier allowlist (injection guard)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,engine,expected",
    [
        ("philceb-api", "postgresql", "philceb_api"),
        ("My App", "postgresql", "my_app"),
        ("weird.name.v2", "mysql", "weird_name_v2"),
        ("9lives", "postgresql", "lives"),
        ("123", "postgresql", "db"),  # all-digits collapses to safe default
        ("a" * 100, "postgresql", "a" * 63),  # truncated to engine max
    ],
)
def test_sanitize_produces_valid_identifier(raw, engine, expected):
    got = p.sanitize_db_name(raw, engine)
    assert got == expected
    assert p.is_valid_identifier(got), f"{got!r} must satisfy the allowlist"


@pytest.mark.parametrize(
    "evil",
    [
        "proj; DROP DATABASE prod",
        "proj9`",
        'proj9"; --',
        "9starts_with_digit",
        "UPPERCASE",
        "has space",
        "",
        "-leading",
    ],
)
def test_identifier_allowlist_rejects_injection(evil):
    assert not p.is_valid_identifier(evil)


def test_sanitize_never_yields_rejected_name():
    """Any raw input must sanitize to something the allowlist accepts."""
    for raw in ["'; DROP TABLE x;--", "../../etc", "北京", "  ", "$$$", "a-b-c"]:
        assert p.is_valid_identifier(p.sanitize_db_name(raw, "postgresql"))


# ---------------------------------------------------------------------------
# DSN construction — never a fake password, never ":@"
# ---------------------------------------------------------------------------


def test_dsn_passwordless_has_no_empty_credentials():
    dsn = p.default_dsn("postgresql", "proj9")
    assert ":@" not in dsn
    assert "postgres@localhost" in dsn


def test_dsn_with_password_embeds_it():
    dsn = p.default_dsn("postgresql", "proj9", password="s3cret")
    assert "postgres:s3cret@" in dsn


# ---------------------------------------------------------------------------
# Detection — signal ordering + GUI clients never used
# ---------------------------------------------------------------------------


def test_detect_uses_client_signal_first():
    det = p.detect_server(
        "postgresql",
        which=lambda _b: "/usr/bin/psql",
        port_probe=lambda *_: False,
    )
    assert det.reachable and det.signal == "client"


def test_detect_falls_back_to_port_probe():
    det = p.detect_server(
        "postgresql",
        which=lambda _b: None,
        port_probe=lambda *_: True,
    )
    assert det.reachable and det.signal == "port"


def test_detect_reports_unreachable_when_no_signal():
    det = p.detect_server(
        "postgresql",
        which=lambda _b: None,
        port_probe=lambda *_: False,
    )
    assert not det.reachable and det.signal == "none"


# ---------------------------------------------------------------------------
# Provisioning decision tree
# ---------------------------------------------------------------------------


def _DET_OK(e, host="localhost"):
    return p.Detection(e, True, "client", "psql · port 5432", host, 5432)


def _DET_NO(e, host="localhost"):
    return p.Detection(e, False, "none", "no server", host, 5432)


def test_provision_online_passwordless_success():
    r = p.provision_database(
        "postgresql",
        "proj9",
        detector=_DET_OK,
        creator=lambda *a: True,
        prompt_password=None,
    )
    assert r.mode == "online" and r.created and not r.offline


def test_provision_unreachable_falls_back_offline():
    r = p.provision_database(
        "postgresql", "proj9", detector=_DET_NO, prompt_password=None
    )
    assert r.offline and r.mode == "offline" and r.engine == "sqlite"
    assert r.dsn == p.OFFLINE_SQLITE_URL
    assert r.ok  # init must still complete


def test_provision_auth_retry_then_success():
    def creator(engine, host, port, user, pw, name):
        if pw == "right":
            return True
        raise p.AuthError("bad password")

    seen = []

    def prompt(ctx):
        seen.append(ctx.attempt)
        return "wrong" if ctx.attempt == 1 else "right"

    r = p.provision_database(
        "postgresql", "proj9", detector=_DET_OK, creator=creator, prompt_password=prompt
    )
    assert r.mode == "online" and r.password_entered and seen == [1, 2]


def test_provision_blank_password_skips_to_offline():
    def creator(engine, host, port, user, pw, name):
        raise p.AuthError("needs password")

    r = p.provision_database(
        "postgresql",
        "proj9",
        detector=_DET_OK,
        creator=creator,
        prompt_password=lambda ctx: None,
    )
    assert r.offline


def test_provision_three_failures_then_offline():
    def creator(engine, host, port, user, pw, name):
        raise p.AuthError("nope")

    attempts = []

    def prompt(ctx):
        attempts.append(ctx.attempt)
        return "still-wrong"

    r = p.provision_database(
        "postgresql", "proj9", detector=_DET_OK, creator=creator, prompt_password=prompt
    )
    assert r.offline and attempts == [1, 2, 3]


def test_provision_privilege_failure_shows_manual_sql():
    def creator(engine, host, port, user, pw, name):
        raise p.PrivilegeError("permission denied")

    r = p.provision_database(
        "postgresql", "proj9", detector=_DET_OK, creator=creator, prompt_password=None
    )
    assert not r.offline and r.manual_sql == "CREATE DATABASE proj9;"


def test_provision_non_interactive_auth_takes_offline():
    def creator(engine, host, port, user, pw, name):
        raise p.AuthError("needs password")

    # prompt_password=None means non-interactive: never block, fall back offline.
    r = p.provision_database(
        "postgresql", "proj9", detector=_DET_OK, creator=creator, prompt_password=None
    )
    assert r.offline


def test_provision_skip_scaffolds_only():
    r = p.provision_database(
        "postgresql", "proj9", skip=True, detector=_DET_OK, prompt_password=None
    )
    assert not r.offline and not r.created and "scaffolded" in r.message.lower()


def test_provision_mongo_is_lazy_no_op():
    r = p.provision_database(
        "mongodb",
        "proj9",
        detector=_DET_OK,
        creator=lambda *a: True,
        prompt_password=None,
    )
    assert r.mode == "online" and "lazily" in r.message


def test_provision_sqlite_needs_no_server():
    r = p.provision_database("sqlite", "proj9", detector=_DET_NO, prompt_password=None)
    assert r.mode == "online" and r.engine == "sqlite" and not r.offline


def test_password_never_appears_in_result_message():
    """The entered password must never leak into any user-facing message/DSN field."""

    def creator(engine, host, port, user, pw, name):
        return True

    r = p.provision_database(
        "postgresql",
        "proj9",
        detector=_DET_OK,
        creator=creator,
        prompt_password=lambda ctx: "SUPER_SECRET_PW",
    )
    assert "SUPER_SECRET_PW" not in r.message
    # DSN legitimately holds the password; callers mask it before printing.


# ---------------------------------------------------------------------------
# Persistence — password only in .env.development, mode recorded in config
# ---------------------------------------------------------------------------


def test_persist_writes_password_only_to_env_development(tmp_path: Path):
    from kaira.commands.db_cmd import _persist_provision

    (tmp_path / ".env").write_text("APP_ENV=development\n", encoding="utf-8")
    (tmp_path / ".kaira.json").write_text(
        json.dumps({"db_type": "postgresql"}), encoding="utf-8"
    )

    result = p.ProvisionResult(
        ok=True,
        mode="online",
        engine="postgresql",
        db_name="proj9",
        dsn="postgresql+asyncpg://postgres:s3cret@localhost:5432/proj9",
        offline=False,
        created=True,
        password_entered=True,
        message="created",
    )
    _persist_provision(tmp_path, "postgresql", result)

    env = (tmp_path / ".env").read_text(encoding="utf-8")
    env_dev = (tmp_path / ".env.development").read_text(encoding="utf-8")
    cfg = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))

    assert "s3cret" not in env, "secret must never land in .env"
    assert "s3cret" in env_dev, "secret belongs in git-ignored .env.development"
    assert "DB_MODE=online" in env
    assert "FALLBACK_MODE=off" in env
    assert (
        cfg["db_name"] == "proj9"
        and cfg["db_provisioned"] is True
        and cfg["db_mode"] == "online"
    )


def test_persist_offline_records_offline_mode(tmp_path: Path):
    from kaira.commands.db_cmd import _persist_provision

    (tmp_path / ".env").write_text("APP_ENV=development\n", encoding="utf-8")
    (tmp_path / ".kaira.json").write_text(
        json.dumps({"db_type": "postgresql"}), encoding="utf-8"
    )

    result = p.ProvisionResult(
        ok=True,
        mode="offline",
        engine="sqlite",
        db_name="proj9",
        dsn=p.OFFLINE_SQLITE_URL,
        offline=True,
        message="offline",
    )
    _persist_provision(tmp_path, "postgresql", result)

    env = (tmp_path / ".env").read_text(encoding="utf-8")
    cfg = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))
    assert "DB_MODE=offline" in env
    assert cfg["db_provisioned"] is False and cfg["db_mode"] == "offline"


# ---------------------------------------------------------------------------
# Offline store matches the data-model family (§3.3) + type fidelity (§3.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "engine,expected_prefix,expected_name",
    [
        ("postgresql", "sqlite", "sqlite"),
        ("mysql", "sqlite", "sqlite"),
        ("sqlite", "sqlite", "sqlite"),
        ("mongodb", "mongodb", "mongodb"),
    ],
)
def test_offline_store_matches_family(engine, expected_prefix, expected_name):
    url = p.offline_store_url(engine, "proj9")
    assert url.startswith(expected_prefix)
    assert p.offline_engine_name(engine) == expected_name


def test_mongo_offline_is_never_sqlite():
    url = p.offline_store_url("mongodb", "proj9")
    assert "sqlite" not in url and url.startswith("mongodb://")


def test_native_type_detection_flags_jsonb_only():
    models = [
        {"name": "Order", "fields": [{"name": "meta", "type": "JSONB"}]},
        {"name": "User", "fields": [{"name": "email", "type": "str"}]},
    ]
    assert p.models_with_native_types(models) == ["Order"]


def test_native_type_detection_empty_for_portable_models():
    models = [{"name": "User", "fields": [{"name": "email", "type": "str"}]}]
    assert p.models_with_native_types(models) == []


# ---------------------------------------------------------------------------
# Generation integration — mode wiring present on all five surfaces
# ---------------------------------------------------------------------------


@pytest.fixture()
def scaffolded_pg(tmp_path, monkeypatch):
    """Scaffold a postgres project non-interactively and return its path."""
    from typer.testing import CliRunner

    from kaira.main import app

    # PYTEST_CURRENT_TEST is set by pytest, so init skips venv/dependency install.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    result = CliRunner().invoke(
        app,
        [
            "init",
            "proj9",
            "--db",
            "postgresql",
            "--auth",
            "none",
            "--no-docker",
            "--ci",
            "none",
            "--profile",
            "scale",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    return tmp_path / "proj9"


def test_generated_env_has_offline_contract(scaffolded_pg: Path):
    env = (scaffolded_pg / ".env").read_text(encoding="utf-8")
    assert "DB_MODE=online" in env
    assert "OFFLINE_DATABASE_URL=sqlite+aiosqlite:///./.kaira/offline.db" in env
    assert "FALLBACK_MODE=off" in env


def test_generated_db_mode_module_exists(scaffolded_pg: Path):
    assert (scaffolded_pg / "core" / "db_mode.py").exists()


def test_generated_health_reports_db_block_no_dsn(scaffolded_pg: Path):
    main_src = (scaffolded_pg / "main.py").read_text(encoding="utf-8")
    assert '"database"' in main_src
    assert "db_engine_name" in main_src and "db_mode" in main_src
    # health block must not embed the DSN
    assert "DATABASE_URL" not in main_src.split("/health")[-1]


def test_generated_middleware_sets_mode_header(scaffolded_pg: Path):
    sec = (scaffolded_pg / "middleware" / "security.py").read_text(encoding="utf-8")
    assert "X-Kaira-DB-Mode" in sec
    assert "db_mode" in sec


def test_generated_settings_have_mode_fields(scaffolded_pg: Path):
    settings = (scaffolded_pg / "config" / "settings.py").read_text(encoding="utf-8")
    assert "DB_MODE" in settings
    assert "OFFLINE_DATABASE_URL" in settings
    assert "FALLBACK_MODE" in settings


def test_generated_logger_has_intercept_handler(scaffolded_pg: Path):
    logger_src = (scaffolded_pg / "core" / "logger.py").read_text(encoding="utf-8")
    assert "InterceptHandler" in logger_src
    assert "sqlalchemy.engine" in logger_src
    assert "KAIRA_SQL_ECHO" in logger_src


def test_generated_database_echo_off_by_default(scaffolded_pg: Path):
    db_src = (scaffolded_pg / "core" / "database.py").read_text(encoding="utf-8")
    assert 'os.getenv("KAIRA_SQL_ECHO")' in db_src
    assert "settings.DEBUG" not in db_src  # echo no longer tied to DEBUG


def test_run_banner_reads_mode_from_config(scaffolded_pg: Path):
    from kaira.commands.run_cmd import _db_banner_info

    info = _db_banner_info(scaffolded_pg)
    assert info is not None
    engine, name, mode, online = info
    assert engine == "postgresql" and name == "proj9" and mode == "online" and online


def test_status_command_shows_mode(scaffolded_pg: Path, monkeypatch):
    from typer.testing import CliRunner

    from kaira.main import app

    monkeypatch.chdir(scaffolded_pg)
    out = CliRunner().invoke(app, ["status"]).output
    assert "proj9" in out and ("online" in out or "offline" in out)


# ---------------------------------------------------------------------------
# Additional coverage — DSN branches, dispatch, detection, edge cases
# ---------------------------------------------------------------------------


def test_default_dsn_all_engines():
    assert p.default_dsn("mysql", "db", password="x", user="root").startswith(
        "mysql+aiomysql://root:x@"
    )
    assert p.default_dsn("mysql", "db").startswith("mysql+aiomysql://root@")
    assert p.default_dsn("mongodb", "db").startswith("mongodb://localhost")
    assert p.default_dsn("mongodb", "db", password="x", user="u").startswith(
        "mongodb://u:x@"
    )
    assert p.default_dsn("sqlite", "db") == p.OFFLINE_SQLITE_URL


def test_manual_create_sql_per_engine():
    assert p.manual_create_sql("postgresql", "proj9") == "CREATE DATABASE proj9;"
    assert p.manual_create_sql("mysql", "proj9") == "CREATE DATABASE `proj9`;"


def test_run_async_executes_coroutine():
    async def _echo():
        return 42

    assert p._run_async(_echo()) == 42


def test_create_dispatch_rejects_unknown_engine():
    with pytest.raises(ValueError):
        p._create_dispatch("oracle", "localhost", 1521, "u", "pw", "db")


def test_port_open_true_on_bound_socket():
    import socket

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert p._port_open("127.0.0.1", port, timeout=1.0) is True
    finally:
        srv.close()


def test_port_open_false_on_closed_port():
    # Port 1 is not listening in a normal test environment.
    assert p._port_open("127.0.0.1", 1, timeout=0.5) is False


def test_detect_sqlite_is_always_reachable():
    det = p.detect_server("sqlite")
    assert det.reachable and det.signal == "client"


def test_provision_driver_missing_scaffolds_dsn():
    def creator(*_a):
        raise ImportError("asyncpg not installed")

    r = p.provision_database(
        "postgresql", "proj9", detector=_DET_OK, creator=creator, prompt_password=None
    )
    assert not r.offline and not r.created and "driver" in r.message.lower()


def test_provision_rejects_invalid_explicit_name():
    r = p.provision_database(
        "postgresql",
        "proj9",
        db_name="Bad Name!",
        detector=_DET_OK,
        prompt_password=None,
    )
    assert not r.ok and "invalid" in r.message.lower()


def test_provision_announces_sanitized_name():
    seen: list[str] = []
    r = p.provision_database(
        "postgresql",
        "Philceb-API",
        detector=_DET_OK,
        creator=lambda *a: True,
        prompt_password=None,
        announce=seen.append,
    )
    assert r.db_name == "philceb_api"
    assert any("sanitized" in m for m in seen)


def test_provision_mysql_offline_is_sqlite():
    r = p.provision_database("mysql", "proj9", detector=_DET_NO, prompt_password=None)
    assert r.offline and r.engine == "sqlite" and r.dsn == p.OFFLINE_SQLITE_URL


def test_provision_mongo_unreachable_offline_is_mongo():
    r = p.provision_database("mongodb", "proj9", detector=_DET_NO, prompt_password=None)
    assert r.offline and r.engine == "mongodb" and "sqlite" not in r.dsn


def test_env_password_reads_pgpassword(monkeypatch):
    from kaira.commands.db_cmd import _env_password

    monkeypatch.setenv("PGPASSWORD", "frompg")
    assert _env_password("postgresql") == "frompg"
    monkeypatch.setenv("MYSQL_PWD", "frommysql")
    assert _env_password("mysql") == "frommysql"
    assert _env_password("mongodb") is None


def test_env_password_env_flows_into_provision():
    """A password already in the environment connects with no prompt."""
    captured = {}

    def creator(engine, host, port, user, pw, name):
        captured["pw"] = pw
        return True

    r = p.provision_database(
        "postgresql",
        "proj9",
        detector=_DET_OK,
        creator=creator,
        env_password="envpass",
        prompt_password=None,
    )
    assert r.mode == "online" and captured["pw"] == "envpass" and not r.password_entered


def test_offline_sqlite_url_helper():
    assert p.offline_sqlite_url() == p.OFFLINE_SQLITE_URL


def test_provision_privilege_failure_after_prompt():
    def creator(engine, host, port, user, pw, name):
        # Passwordless attempt fails auth (falls to prompt); prompted attempt
        # authenticates but the user lacks CREATE DATABASE privilege.
        if not pw:
            raise p.AuthError("needs password")
        raise p.PrivilegeError("permission denied")

    r = p.provision_database(
        "postgresql",
        "proj9",
        detector=_DET_OK,
        creator=creator,
        prompt_password=lambda ctx: "somepass",
    )
    assert not r.offline and r.manual_sql == "CREATE DATABASE proj9;"


def test_native_types_ignore_typeless_fields():
    models = [{"name": "M", "fields": [{"name": "x"}]}]  # no "type" key
    assert p.models_with_native_types(models) == []


class _FakePGConn:
    def __init__(self, existing: bool):
        self._existing = existing
        self.executed: list[str] = []

    async def fetchval(self, query, *args):
        return 1 if self._existing else None

    async def execute(self, query):
        self.executed.append(query)

    async def close(self):
        pass


def _install_fake_asyncpg(monkeypatch, conn):
    import sys
    import types

    fake = types.ModuleType("asyncpg")
    fake.InvalidPasswordError = type("InvalidPasswordError", (Exception,), {})
    fake.InvalidAuthorizationSpecificationError = type(
        "InvalidAuthorizationSpecificationError", (Exception,), {}
    )

    async def _connect(dsn, timeout=5):
        return conn

    fake.connect = _connect
    monkeypatch.setitem(sys.modules, "asyncpg", fake)
    return fake


def test_pg_create_creates_when_absent(monkeypatch):
    conn = _FakePGConn(existing=False)
    _install_fake_asyncpg(monkeypatch, conn)
    created = p._run_async(
        p._pg_create("postgresql://postgres@localhost:5432/postgres", "proj9")
    )
    assert created is True
    assert conn.executed == ['CREATE DATABASE "proj9"']


def test_pg_create_is_idempotent_when_present(monkeypatch):
    conn = _FakePGConn(existing=True)
    _install_fake_asyncpg(monkeypatch, conn)
    created = p._run_async(
        p._pg_create("postgresql://postgres@localhost:5432/postgres", "proj9")
    )
    assert created is False and conn.executed == []


def test_pg_create_rejects_unsafe_identifier(monkeypatch):
    conn = _FakePGConn(existing=False)
    _install_fake_asyncpg(monkeypatch, conn)
    with pytest.raises(ValueError):
        p._run_async(
            p._pg_create("postgresql://postgres@localhost:5432/postgres", "bad; drop")
        )


def test_create_dispatch_postgres_goes_through_pg_create(monkeypatch):
    conn = _FakePGConn(existing=False)
    _install_fake_asyncpg(monkeypatch, conn)
    created = p._create_dispatch(
        "postgresql", "localhost", 5432, "postgres", "", "proj9"
    )
    assert created is True and conn.executed == ['CREATE DATABASE "proj9"']


def test_set_env_active_replaces_in_place(tmp_path: Path):
    from kaira.commands.db_cmd import _set_env_active

    f = tmp_path / ".env"
    f.write_text("DB_MODE=online\nDEBUG=True\n", encoding="utf-8")
    _set_env_active("DB_MODE", "offline", [f])
    _set_env_active("NEW_KEY", "v", [f])
    content = f.read_text(encoding="utf-8")
    assert content.count("DB_MODE=") == 1 and "DB_MODE=offline" in content
    assert "NEW_KEY=v" in content and "DEBUG=True" in content
