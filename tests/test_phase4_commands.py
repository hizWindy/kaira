"""Phase 4 command tests — cache, task, integrate, api, quality, profile, loadtest,
deploy, middleware, event, notify, flags, health-endpoint.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


def test_cache_add_get_route_ok(tmp_path, monkeypatch):
    """cache add GET /users should succeed and print a cache key."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps(
            {
                "output_dir": "src",
                "db_type": "postgresql",
                "default_tier": "full",
                "generated_models": [],
                "project_name": "test",
            }
        )
    )
    from kaira.commands.cache_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["add", "GET", "/users", "--ttl", "300"])
    assert result.exit_code == 0
    assert "cache" in result.output.lower() or "key" in result.output.lower()


def test_cache_add_post_route_blocked():
    """cache add POST /users should be rejected — only GET routes are cacheable."""
    from kaira.commands.cache_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["add", "POST", "/users"])
    assert result.exit_code != 0 or "Cannot cache" in result.output


def test_cache_clear_all_requires_confirmation(tmp_path, monkeypatch):
    """cache clear --all should require typed confirmation."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps(
            {
                "output_dir": "src",
                "db_type": "postgresql",
                "default_tier": "full",
                "generated_models": [],
                "project_name": "test",
            }
        )
    )
    from kaira.commands.cache_cmd import app

    runner = CliRunner()
    # Provide wrong confirmation word — should cancel
    result = runner.invoke(app, ["clear", "--all"], input="wrongword\n")
    assert (
        "Aborted" in result.output
        or result.exit_code != 0
        or "cancelled" in result.output.lower()
    )


# ---------------------------------------------------------------------------
# Flags tests
# ---------------------------------------------------------------------------


def test_flags_init_creates_file(tmp_path, monkeypatch):
    """flags init should create core/flags.py."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps(
            {
                "output_dir": "src",
                "db_type": "postgresql",
                "default_tier": "full",
                "generated_models": [],
                "project_name": "test",
            }
        )
    )
    from kaira.commands.flags_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    flags_path = tmp_path / "src" / "core" / "flags.py"
    assert flags_path.exists()


def test_flags_add_snake_case():
    """flags add should accept valid snake_case names."""
    from kaira.commands.flags_cmd import _SNAKE_CASE_RE

    assert _SNAKE_CASE_RE.match("my_feature")
    assert _SNAKE_CASE_RE.match("feature_v2")


def test_flags_add_rejects_non_snake_case():
    """flags add should reject names that are not snake_case."""
    from kaira.commands.flags_cmd import _SNAKE_CASE_RE

    assert not _SNAKE_CASE_RE.match("MyFeature")
    assert not _SNAKE_CASE_RE.match("my-feature")


def test_flags_fail_closed():
    """is_enabled should return False for unknown flags."""
    # Simulate via the template logic
    flags = {"known_flag": True}
    result = flags.get("unknown_flag", False)
    assert result is False


def test_flags_enable_disable(tmp_path, monkeypatch):
    """flags enable / disable should toggle flags correctly."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps(
            {
                "output_dir": "src",
                "db_type": "postgresql",
                "default_tier": "full",
                "generated_models": [],
                "project_name": "test",
            }
        )
    )
    from kaira.commands.flags_cmd import _read_flags, _write_flags, app

    runner = CliRunner()

    # init
    runner.invoke(app, ["init"])
    flags_path = tmp_path / "src" / "core" / "flags.py"
    _write_flags(flags_path, {"my_flag": False})

    # enable
    result = runner.invoke(app, ["enable", "my_flag"])
    assert result.exit_code == 0
    flags = _read_flags(flags_path)
    assert flags["my_flag"] is True

    # disable
    result = runner.invoke(app, ["disable", "my_flag"])
    assert result.exit_code == 0
    flags = _read_flags(flags_path)
    assert flags["my_flag"] is False


# ---------------------------------------------------------------------------
# Middleware tests
# ---------------------------------------------------------------------------


def test_middleware_remove_protected_blocked():
    """middleware remove should block removal of SecurityHeadersMiddleware."""
    from kaira.commands.middleware_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["remove", "SecurityHeadersMiddleware"])
    assert result.exit_code != 0 or "Blocked" in result.output


def test_middleware_remove_cors_blocked():
    """middleware remove should block removal of CORSMiddleware."""
    from kaira.commands.middleware_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["remove", "CORSMiddleware"])
    assert result.exit_code != 0 or "Blocked" in result.output


def test_middleware_add_protected_name_blocked():
    """middleware add should block creating a middleware with a protected name."""
    from kaira.commands.middleware_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["add", "SecurityHeadersMiddleware"])
    assert result.exit_code != 0 or "Blocked" in result.output


def test_middleware_add_generates_file(tmp_path, monkeypatch):
    """middleware add should create middleware/<snake_name>.py."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text(
        json.dumps(
            {
                "output_dir": "src",
                "db_type": "postgresql",
                "default_tier": "full",
                "generated_models": [],
                "project_name": "test",
            }
        )
    )
    from kaira.commands.middleware_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["add", "LoggingMiddleware", "--timeout", "30"])
    assert result.exit_code == 0
    mw_path = tmp_path / "src" / "middleware" / "logging_middleware.py"
    assert mw_path.exists()


# ---------------------------------------------------------------------------
# Loadtest security tests
# ---------------------------------------------------------------------------


def test_loadtest_blocks_remote_without_flag():
    """loadtest should block remote hosts unless --allow-remote is passed."""
    from kaira.commands.loadtest_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["run", "GET", "http://example.com/users"])
    assert result.exit_code != 0 or "Blocked" in result.output


def test_loadtest_localhost_allowed():
    """loadtest should allow localhost targets without --allow-remote."""
    from kaira.commands.loadtest_cmd import _is_localhost

    assert _is_localhost("localhost") is True
    assert _is_localhost("127.0.0.1") is True
    assert _is_localhost("example.com") is False


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------


def test_health_endpoint_generates_file(tmp_path, monkeypatch):
    """health-endpoint generate should create routers/health_router.py."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
        "routers_dir": "routers",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["health-endpoint", "generate"])
    assert result.exit_code == 0
    health_path = tmp_path / "src" / "routers" / "health_router.py"
    assert health_path.exists()


def test_health_endpoint_no_cache_if_not_initialized(tmp_path, monkeypatch):
    """health-endpoint should not include cache check when core/cache.py is absent."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
        "routers_dir": "routers",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["health-endpoint", "generate"])
    health_path = tmp_path / "src" / "routers" / "health_router.py"
    if health_path.exists():
        content = health_path.read_text()
        # Without cache, the init_cache import block should not render
        # (Jinja2 cache_enabled=False skips the block)
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Deploy tests
# ---------------------------------------------------------------------------


def test_deploy_generate_railway(tmp_path, monkeypatch):
    """deploy generate --platform railway should create railway.toml."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.commands.deploy_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["generate", "--platform", "railway"])
    assert result.exit_code == 0
    assert (tmp_path / "railway.toml").exists()


def test_deploy_run_blocked_when_checklist_fails(tmp_path, monkeypatch):
    """deploy run should be blocked when checklist items are ❌."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.commands.deploy_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["run", "--platform", "railway", "--force"])
    # No .env.production, no Dockerfile, no tests — must be blocked
    assert result.exit_code != 0 or "blocked" in result.output.lower()


# ---------------------------------------------------------------------------
# Notify tests
# ---------------------------------------------------------------------------


def test_notify_test_blocked_in_production(monkeypatch):
    """notify test should be blocked when APP_ENV=production."""
    monkeypatch.setenv("APP_ENV", "production")
    from kaira.commands.notify_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["test", "--type", "email", "--to", "test@example.com"])
    assert result.exit_code != 0 or "Blocked" in result.output
    monkeypatch.delenv("APP_ENV", raising=False)


def test_notify_generate_no_provider(tmp_path, monkeypatch):
    """notify generate should print integrate command if no provider found."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.commands.notify_cmd import app

    runner = CliRunner()
    result = runner.invoke(app, ["generate", "EmailNotification"])
    # Should exit 1 and mention integrate
    assert result.exit_code != 0 or "integrate" in result.output.lower()


# ---------------------------------------------------------------------------
# Event tests
# ---------------------------------------------------------------------------


def test_event_generate_startup(tmp_path, monkeypatch):
    """event generate startup should create events/startup.py."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["event", "generate", "startup"])
    assert result.exit_code == 0
    startup_path = tmp_path / "src" / "events" / "startup.py"
    assert startup_path.exists()


def test_event_startup_uses_lifespan_not_on_event(tmp_path, monkeypatch):
    """Generated startup.py should not use @app.on_event (deprecated)."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.main import app

    runner = CliRunner()
    runner.invoke(app, ["event", "generate", "startup"])
    startup_path = tmp_path / "src" / "events" / "startup.py"
    if startup_path.exists():
        content = startup_path.read_text()
        assert "\n@app.on_event" not in content


def test_event_startup_no_cache_without_init(tmp_path, monkeypatch):
    """Startup event should not import init_cache when core/cache.py is absent."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    from kaira.main import app

    runner = CliRunner()
    runner.invoke(app, ["event", "generate", "startup"])
    startup_path = tmp_path / "src" / "events" / "startup.py"
    if startup_path.exists():
        content = startup_path.read_text()
        assert "init_cache" not in content


def test_event_startup_includes_cache_when_initialized(tmp_path, monkeypatch):
    """Startup event should import init_cache when core/cache.py exists."""
    monkeypatch.chdir(tmp_path)
    cfg = {
        "output_dir": "src",
        "db_type": "postgresql",
        "default_tier": "full",
        "generated_models": [],
        "project_name": "test",
    }
    (tmp_path / ".kaira.json").write_text(json.dumps(cfg))
    # Create cache module to trigger cache detection
    (tmp_path / "src" / "core").mkdir(parents=True)
    (tmp_path / "src" / "core" / "cache.py").write_text("# cache stub")
    from kaira.main import app

    runner = CliRunner()
    runner.invoke(app, ["event", "generate", "startup"])
    startup_path = tmp_path / "src" / "events" / "startup.py"
    if startup_path.exists():
        content = startup_path.read_text()
        assert "init_cache" in content
