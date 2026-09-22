---
name: kaira-orchestrator
description: Central orchestrator for the Kaira framework migration. Manages sub-agent dispatch, phase gates, and cross-agent consistency.
---

# Kaira Orchestrator

## Purpose

Central coordinator that drives the Kaira framework migration across all sub-agents. Ensures phases complete in order, tests pass between phases, and cross-agent consistency is maintained.

## Architecture

```
Orchestrator
 ├── kaira-template-agent      → Phase 1: Template & Dependencies
 ├── kaira-cli-refactor-agent  → Phase 2: CLI Command Refactor
 ├── kaira-runtime-agent       → Phase 3: Runtime Default
 ├── kaira-test-agent          → Phase 4: Test Updates
 └── kaira-framework-migration  → Master skill (this document)
```

## Phase Sequencing

### Phase 1 → Phase 2 Gate
- Template agent completes all Phase 1 tasks
- Orchestrator verifies: `kaira init` produces `main.py` with `KairaApp`
- Orchestrator runs: `pytest tests/test_commands.py -v`
- If PASS → dispatch CLI refactor agent
- If FAIL → block, report failure, retry

### Phase 2 → Phase 3 Gate
- CLI refactor agent completes all Phase 2 tasks
- Orchestrator verifies: no string-splicing remains in `kaira/commands/` and `kaira/core/`
- Orchestrator runs: `pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v`
- If PASS → dispatch runtime agent
- If FAIL → block, report failure, retry

### Phase 3 → Phase 4 Gate
- Runtime agent completes all Phase 3 tasks
- Orchestrator verifies: `kaira run` uses `KairaApp`, no `--framework` flag
- Orchestrator runs: `pytest tests/test_commands.py -v && pytest tests/test_shortcuts.py -v`
- If PASS → dispatch test agent
- If FAIL → block, report failure, retry

### Phase 4 Gate (Final)
- Test agent completes all Phase 4 tasks
- Orchestrator runs: `pytest` (full suite)
- If PASS → migration complete
- If FAIL → block, report failure, retry

## Sub-Agent Dispatch Rules

1. **One sub-agent at a time** — phases are sequential, not parallel
2. **Sub-agent reads its SKILL.md** for task instructions
3. **Sub-agent reports completion** with a summary of changes made
4. **Orchestrator validates** before dispatching next agent
5. **No agent may skip a phase gate**

## Cross-Agent Consistency

1. **Template agent must complete before CLI refactor agent starts** — CLI commands depend on knowing the template structure
2. **CLI refactor agent must complete before runtime agent starts** — Runtime changes depend on CLI commands being refactored
3. **Test agent reads the current codebase** — does not assume previous agent's output
4. **All agents reference `kaira/__init__.py`** for understanding the `_KairaSubmoduleFinder` and `khaira.*` import routing
5. **All agents reference `kaira/app/__init__.py`** for understanding `KairaApp` exports

## Key Files to Modify

### Phase 1
- `kaira/commands/project.py` — template selection
- `kaira/templates/requirements.txt.j2` — add `khaira`
- `kaira/templates/pyproject_generated.toml.j2` — add `khaira`
- `kaira/templates/main_app.py.j2` — context update
- `kaira/templates/main_simple.py.j2` — update to use `KairaApp`

### Phase 2
- `kaira/core/wiring.py` — remove string-splicing
- `kaira/commands/monitor_cmd.py` — replace `splice_main()`, `splice_sdk_init()`
- `kaira/commands/auth_cmd.py` — replace `register_router_in_main()` call
- `kaira/commands/event_cmd.py` — replace manual instructions
- `kaira/commands/middleware_cmd.py` — replace manual instructions
- `kaira/commands/generate.py` — remove `_register_router_in_main()` call
- `kaira/commands/ai_cmd.py` — replace string-splicing

### Phase 3
- `kaira/commands/run_cmd.py` — default to `KairaApp`
- `kaira/templates/main_app_v3.py.j2` — remove
- `kaira/commands/project.py` — `upgrade` command deprecation
- String anchor constants across all files

### Phase 4
- `tests/test_commands.py` — add `KairaApp` assertions
- `tests/test_phase4_wiring.py` — update assertions
- `tests/test_runtime.py` — new file

## Test Commands

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

All prompts use `kaira.core.prompts`. Non-TTY degrades gracefully. This applies to agents too — when executing commands in CI, use flags like `--yes` and `--non-interactive`.
