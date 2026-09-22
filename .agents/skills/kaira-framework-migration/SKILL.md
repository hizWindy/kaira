---
name: kaira-framework-migration
description: Orchestrates the Kaira framework migration from scaffolding tool to full runtime framework. Manages phases, gates, and cross-agent consistency.
---

# Kaira Framework Migration — Orchestrator

## Purpose

This skill drives the migration of Kaira from a "Zero-Lock-in Scaffolding Tool" to a "Full-Fledged Framework Runtime" where `KairaApp` is the default entry point.

## Core Invariants

1. **KairaApp is the default**: Every newly scaffolded project MUST use `KairaApp` from `kaira.app`.
2. **No string-splicing**: No CLI command may manipulate `main.py` via string replacement (`content.replace`, anchor markers). All registration must use `KairaApp.register_router()` and `app.register_provider()`.
3. **khaira is a dependency**: Every generated project MUST list `khaira` in `requirements.txt` and `pyproject_generated.toml`.
4. **kaira run uses KairaApp**: `kaira run` MUST instantiate and call `KairaApp().run()`, not delegate to `subprocess.run(["fastapi", ...])`.
5. **Tests pass between phases**: No phase may proceed until the previous phase's tests pass.

## Phase Gates

### Phase 1: Template & Dependencies Flip (MUST complete first)
- [ ] `project.py` renders `main_app.py.j2` instead of `main_app_v3.py.j2`
- [ ] `requirements.txt.j2` includes `khaira>=0.2.3`
- [ ] `pyproject_generated.toml.j2` includes `khaira>=0.2.3`
- [ ] `main_app.py.j2` context includes `providers`, `enforce_layers`, `kaira_version`
- [ ] `main_simple.py.j2` extends `KairaApp` for consistency
- [ ] Test pass status: RUN `pytest tests/test_commands.py -v`

### Phase 2: CLI Command Refactor (Eliminate String-Splicing)
- [ ] `wiring.py` uses `KairaApp.register_router()` instead of `ROUTER_MARKER`/`IMPORT_ANCHOR`
- [ ] `monitor_cmd.py` uses `app.register_provider(MonitorProvider())` instead of `splice_main()`
- [ ] `event_cmd.py` uses `app.register_lifecycle_hook()` instead of printing manual instructions
- [ ] `middleware_cmd.py` uses `app.add_middleware()` programmatically
- [ ] `auth_cmd.py` uses `app.register_router()` instead of `register_router_in_main()`
- [ ] `ai_cmd.py` uses `app.register_router()` instead of string-splicing
- [ ] All string anchors removed: `ROUTER_MARKER`, `IMPORT_ANCHOR`, `_LIFESPAN_ANCHOR`, `_SECURITY_CALL`, `_ROUTER_MARKER`
- [ ] Test pass status: RUN `pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v`

### Phase 3: Runtime Default
- [ ] `run_cmd.py` defaults to `KairaApp().run()` without `--framework` flag
- [ ] `--framework` flag removed or deprecated
- [ ] `_find_entry()`, `_module_from_path()` logic removed
- [ ] `kaira upgrade` deprecated or removed
- [ ] `main_app_v3.py.j2` removed
- [ ] Test pass status: RUN `pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v`

### Phase 4: Test Updates & Cleanup
- [ ] Tests updated for `KairaApp`-based initialization
- [ ] Tests updated for `kaira run` invoking `KairaApp().run()`
- [ ] Integration tests for `kaira init` producing `main.py` with `KairaApp`
- [ ] Integration tests for `kaira run` invoking `KairaApp`
- [ ] Generated `requirements.txt` includes `khaira`
- [ ] Generated `pyproject_generated.toml` includes `khaira`
- [ ] Test pass status: RUN `pytest` (full suite)

## Cross-Agent Consistency Rules

1. **Template changes must be verified before CLI changes**: The CLI agent must see the updated `main.py` structure before refactoring commands.
2. **No agent may skip a phase gate**: If tests fail, the orchestrator blocks the next phase.
3. **All string-splicing must be replaced, not duplicated**: If a new CLI command needs to modify `main.py`, it MUST use `KairaApp.register_router()` or `app.register_provider()`.
4. **The `_KairaSubmoduleFinder` in `kaira/__init__.py` handles `khaira.*` imports**: Do NOT create physical `khaira/` subpackages. The meta-path finder routes `khaira.http` → `kaira.app.http` automatically.

## Key Files Reference

| File | Purpose |
|------|---------|
| `kaira/commands/project.py` | `init` command — renders `main_app.py.j2` |
| `kaira/commands/generate.py` | `generate model` — creates pipeline layers |
| `kaira/core/wiring.py` | Router registration (must be refactored) |
| `kaira/commands/run_cmd.py` | `kaira run` (must use `KairaApp`) |
| `kaira/commands/monitor_cmd.py` | `monitor init` (must use providers) |
| `kaira/commands/auth_cmd.py` | `auth register` (must use `register_router`) |
| `kaira/commands/event_cmd.py` | `event` commands |
| `kaira/commands/middleware_cmd.py` | `middleware` commands |
| `kaira/templates/main_app.py.j2` | `KairaApp` entry template |
| `kaira/templates/main_app_v3.py.j2` | OLD template — remove after migration |
| `kaira/templates/requirements.txt.j2` | Generated dependencies |
| `kaira/templates/pyproject_generated.toml.j2` | Generated pyproject |
| `kaira/app/kaira_app.py` | `KairaApp` runtime |
| `kaira/app/__init__.py` | Framework exports |
| `kaira/__init__.py` | `_KairaSubmoduleFinder` for `khaira.*` imports |

## Testing Commands

```bash
# Phase 1 gate
pytest tests/test_commands.py -v

# Phase 2 gate
pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v

# Phase 3 gate
pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v

# Phase 4 gate (full suite)
pytest
```

## Non-TTY Safety

All prompts must use `kaira.core.prompts`. When stdin is not a TTY, prompts must degrade gracefully with the exact CLI flag to pass.
