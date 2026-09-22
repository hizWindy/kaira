---
name: kaira-cli-refactor-agent
description: Refactors all Kaira CLI commands to eliminate string-splicing of main.py and replace with KairaApp programmatic API calls.
---

# Kaira CLI Refactor Agent

## Scope

Responsible for Phase 2 of the Kaira framework migration: eliminating all string-splicing in CLI commands and replacing with `KairaApp` programmatic API calls.

## Anti-Pattern: String-Splicing

String-splicing is the practice of reading `main.py`, finding marker strings, and replacing them. This is fragile and breaks when templates change. ALL instances must be eliminated.

## Tasks

### 1. Refactor `kaira/core/wiring.py`

**Current**: Uses `ROUTER_MARKER = "# [ROUTER_REGISTRATION]"` and `IMPORT_ANCHOR = "from rate_limit import limiter\n"` to splice routers into `main.py`.

**Replace with**: A function that uses `KairaApp` programmatic API:
```python
def register_router_in_main(main_path: Path, import_line: str, include_line: str) -> str:
    """Register a router using KairaApp programmatic API."""
    # Read existing main.py, use AST to find the app variable,
    # then call app.register_router() programmatically.
    # OR: Simply instruct the user to use app.register_router()
    # since KairaApp auto-discovers routers from routers/ directory.
```

**Key insight**: Since `KairaApp._setup_lazy_registration()` auto-discovers routers from the `routers/` directory, `wiring.py` may become unnecessary entirely. Routers dropped in `routers/` are auto-registered.

### 2. Refactor `kaira/commands/monitor_cmd.py`

**Current**: Uses `_LIFESPAN_ANCHOR`, `_SECURITY_CALL`, `_ROUTER_MARKER`, `_SDK_CALL` to splice monitoring into `main.py`.

**Replace with**: `app.register_provider(MonitorProvider())` and `app.register_provider(ProviderName())`.

The `splice_main()` function should be replaced with:
```python
def wire_monitoring(app_instance):
    """Register monitoring provider with the KairaApp instance."""
    from kaira.app.providers.monitor import MonitorProvider
    app_instance.register_provider(MonitorProvider())
```

Remove all anchor constants: `_LIFESPAN_ANCHOR`, `_SECURITY_CALL`, `_ROUTER_MARKER`, `_SDK_IMPORT`, `_SDK_CALL`, `_SDK_BLOCK`, `_SECURITY_IMPORT`, `_SECURITY_CALL`, `_METRICS_IMPORT`, `_PROBES_IMPORT`, `_PROBES_INCLUDE`, `_MONITOR_IMPORT`, `_MONITOR_INCLUDE`.

### 3. Refactor `kaira/commands/auth_cmd.py`

**Current**: Calls `register_router_in_main()` from `kaira/core/wiring.py`.

**Replace with**: Since `KairaApp` auto-discovers routers from the `routers/` directory, the `auth register` command should simply verify the router file exists in `routers/` and optionally move it there. No `main.py` editing needed.

If explicit registration is needed, use `app_instance.register_router(router, prefix=...)`.

### 4. Refactor `kaira/commands/event_cmd.py`

**Current**: Prints manual instructions for registering lifespan events in `main.py`.

**Replace with**: Use `app.register_lifecycle_hook()` or the `@app.on_event("startup")` decorator. Since `KairaApp` has `LifecycleManager`, events should be registered programmatically.

### 5. Refactor `kaira/commands/middleware_cmd.py`

**Current**: Prints `app.add_middleware({name})` as manual instructions.

**Replace with**: Programmatic `app_instance.add_middleware(MiddlewareClass)`.

### 6. Refactor `kaira/commands/generate.py`

**Current**: `_register_router_in_main()` calls `register_router_in_main()` from `wiring.py`.

**Replace with**: Remove the call entirely. `KairaApp._setup_lazy_registration()` auto-discovers routers from `routers/`. The generated router file in `routers/` will be found automatically.

### 7. Refactor `kaira/commands/ai_cmd.py`

**Current**: Has similar string-splicing pattern to wire AI routers into `main.py`.

**Replace with**: Same approach — drop router files in `routers/` and let `KairaApp` auto-discover them.

## Rules

1. **Never use `content.replace()` on `main.py`**: This is the cardinal sin.
2. **Never search for anchor markers in `main.py`**: `# [ROUTER_REGISTRATION]`, `from rate_limit import limiter`, etc.
3. **Use `KairaApp.register_router()` for explicit registration**
4. **Use `app.register_provider()` for provider registration**
5. **Use `app.add_middleware()` for middleware registration**
6. **Use `app_instance.register_lifecycle_hook()` for lifecycle events**
7. **When in doubt, let `KairaApp` auto-discovery handle it**: Drop files in the correct directory and let `KairaApp._setup_lazy_registration()` find them.

## Verification

- `grep -r "content.replace" kaira/commands/ kaira/core/` should return no results related to `main.py` manipulation
- `grep -r "_ANCHOR\|_MARKER\|_CALL\|_IMPORT" kaira/commands/ kaira/core/` should return no anchor constants
- All CLI commands work without modifying `main.py` string content
- Test pass: `pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v`
