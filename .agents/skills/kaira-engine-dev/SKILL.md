---
name: kaira-engine-dev
description: Guidelines and workflows for AI assistants developing and modifying the Kaira CLI engine codebase.
---

# Contributing to the Kaira CLI Engine

When modifying or extending Kaira (the CLI engine itself), follow these architectural rules and testing workflows.

---

## 1. Directory Overview

- `kaira/main.py`: CLI entrypoint with Typer command groups and alias resolution.
- `kaira/commands/`: Modular command handlers (e.g. `project.py`, `generate.py`, `ai_cmd.py`).
- `kaira/core/`: Core engines (e.g. `wiring.py`, `aliases.py`, `ai_introspect.py`, `detector.py`).
- `kaira/templates/`: Jinja2 templates (*.j2) rendered by the generator into user projects.
- `tests/`: Extensive pytest test suites.

---

## 2. Strict Invariants

1. **5-Layer Architecture**: Generated code must strictly preserve the separation between Model, Repository, Schema, Service, and Router.
2. **Command Shortcuts**: Shortcuts (`g`, `sm`, `mr`, `st`, etc.) are strictly additive; destructive commands (`db reset`, `migrate rollback`, `seed clear`) **MUST NEVER** have shortcuts.
3. **Non-TTY Terminal Safety**: All interactive prompts must use `kaira.core.prompts` and degrade gracefully with a friendly error when stdin is not a TTY.
4. **Local Config State**: Any new models or configuration must be tracked in `.kaira.json`.

---

## 3. Testing Workflows

Always run targeted and full test suites before committing changes:

```bash
# Run command tests
pytest tests/test_commands.py -v

# Run AI command tests
pytest tests/test_ai_cmd.py -v

# Run shortcut tests
pytest tests/test_shortcuts.py -v

# Run full suite
pytest
```
