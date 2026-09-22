---
name: kaira-runtime-agent
description: Makes kaira run use KairaApp as the default runtime instead of delegating to fastapi dev/uvicorn via subprocess.
---

# Kaira Runtime Agent

## Scope

Responsible for Phase 3 of the Kaira framework migration: making `kaira run` use `KairaApp` as the default runtime.

## Current State

`kaira/commands/run_cmd.py` currently delegates to `subprocess.run(["fastapi", "dev", ...])`. The `--framework` flag exists as an opt-in way to use `KairaApp`. This flag must become the default behavior.

## Tasks

### 1. Make `KairaApp` the Default in `run_cmd.py`

**File**: `kaira/commands/run_cmd.py`

**Current flow** (lines 210-232):
```python
if framework:
    from kaira.app import KairaApp
    app_instance = KairaApp(...)
    app_instance.run(dev=not prod, host=host, port=port)
    return
# ... subprocess.run(["fastapi", "dev", ...])
```

**Change**: Remove the `if framework` condition. Always use `KairaApp`.

```python
from kaira.app import KairaApp
from kaira.config import get_config

cfg = get_config()
app_instance = KairaApp(
    project_name=cfg.db_name or cwd.name,
    tier=getattr(cfg, "tier", "standard"),
    providers=getattr(cfg, "providers", ["cache", "auth"]),
)
app_instance.run(dev=not prod, host=host, port=port)
return
```

### 2. Remove `--framework` Flag

Remove the `framework` parameter from `run_command()` callback. It's no longer needed.

### 3. Remove Subprocess Delegation Logic

Remove:
- `_find_entry()` function — no longer needed since `KairaApp` auto-discovers routers
- `_module_from_path()` function — no longer needed
- `_module_importable()` function — no longer needed
- The `fastapi_cli` / `uvicorn_available` detection logic
- The `subprocess.run(cmd, cwd=str(cwd), env=env)` call
- The `record_server()` / `clear_server()` calls (or adapt for KairaApp)
- The `_find_entry` candidate list
- The port resolution logic can stay (for `kaira run --port`)

### 4. Simplify `kaira run` Banner

The banner currently shows runner info (fastapi/uvicorn). Update to show:
- Mode (dev/prod)
- Host/Port
- Database info
- `KairaApp` as the runner

### 5. Deprecate `kaira upgrade`

Since `init` now produces `KairaApp`-based projects by default, `kaira upgrade` is no longer needed. Either remove it or deprecate it with a message.

### 6. Remove `main_app_v3.py.j2`

Delete `kaira/templates/main_app_v3.py.j2`. It's dead code after the template flip.

### 7. Cleanup String Anchors

Remove all dead constants:
- `ROUTER_MARKER`, `IMPORT_ANCHOR` from `kaira/core/wiring.py`
- `_LIFESPAN_ANCHOR`, `_SDK_CALL`, `_SDK_IMPORT`, `_SDK_BLOCK` from `kaira/commands/monitor_cmd.py`
- `_SECURITY_CALL`, `_SECURITY_IMPORT`, `_ROUTER_MARKER` from `kaira/commands/monitor_cmd.py`
- `_METRICS_IMPORT`, `_PROBES_IMPORT`, `_PROBES_INCLUDE`, `_MONITOR_IMPORT`, `_MONITOR_INCLUDE` from `kaira/commands/monitor_cmd.py`

## Rules

1. **`kaira run` MUST call `KairaApp().run()` directly** — never `subprocess.run`
2. **No `--framework` flag** — it's the default
3. **`KairaApp` handles router auto-discovery** — no need to find entry files
4. **Port resolution stays** — `kaira run --port` still works
5. **Environment variable passing stays** — `KAIRA_SQL_ECHO`, `KAIRA_LOG_LEVEL`, etc. still work

## Verification

- `kaira run` starts `KairaApp` without `--framework` flag
- `kaira run --prod` starts `KairaApp` in production mode
- No subprocess calls to `fastapi` or `uvicorn` in `run_cmd.py`
- Test pass: `pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v`
