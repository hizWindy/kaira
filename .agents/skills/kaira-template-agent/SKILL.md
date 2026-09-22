---
name: kaira-template-agent
description: Handles template migration for the Kaira framework migration. Flips init to use KairaApp, adds khaira dependency, ensures template consistency.
---

# Kaira Template Agent

## Scope

Responsible for Phase 1 of the Kaira framework migration: template and dependency changes.

## Tasks

### 1. Flip `project.py` Template Selection

**File**: `kaira/commands/project.py` line ~674

**Change**: Replace `main_app_v3.py.j2` with `main_app.py.j2`:
```python
# BEFORE (line 674)
main_tmpl = env.get_template("main_app_v3.py.j2")

# AFTER
main_tmpl = env.get_template("main_app.py.j2")
```

For `simple` tier, keep `main_simple.py.j2` but ensure it also uses `KairaApp` for consistency.

### 2. Add `khaira` to Generated Dependencies

**File**: `kaira/templates/requirements.txt.j2`

Add to the dependency list:
```
khaira>=0.2.3
```

**File**: `kaira/templates/pyproject_generated.toml.j2`

Add to the dependencies array:
```toml
"khaira>=0.2.3",
```

### 3. Update `main_app.py.j2` Context

**File**: `kaira/commands/project.py` line ~660-668

The context `ctx` must include `providers`, `enforce_layers`, and `kaira_version`:
```python
ctx = {
    "project_name": name,
    "project_slug": slug,
    "db_type": db,
    "auth_type": auth,
    "api_version": "v1",
    "tier": tier,
    "providers": ["cache", "auth"],  # from config
    "enforce_layers": True,           # from config
    "kaira_version": "0.2.3",         # from config
}
```

### 4. Update `main_simple.py.j2`

**File**: `kaira/templates/main_simple.py.j2`

Update to extend `KairaApp` for consistency:
```python
from kaira.app import KairaApp
app = KairaApp(project_name="{{ project_name }}", auto_register=True)
```

## Template Consistency Rules

1. **All templates importing `khaira.*` are valid**: The `_KairaSubmoduleFinder` in `kaira/__init__.py` routes `khaira.http` → `kaira.app.http`, `khaira.schemas` → `kaira.app.schemas`, etc. Do NOT create physical `khaira/` subpackages.
2. **Every `.j2` template that uses `khaira.*` must have `khaira` in generated dependencies**: Verify `requirements.txt.j2` and `pyproject_generated.toml.j2` include `khaira`.
3. **Do NOT modify `main_app_v3.py.j2`**: It will be removed in Phase 3. Just stop rendering it.
4. **`router.py.j2` imports `from khaira.http import Router`**: This is correct. Do NOT change to `from kaira.app.http import Router`.
5. **`schema.py.j2` imports `from khaira.schemas import Schema`**: Correct. Do not change.
6. **`model.py.j2` imports `from khaira.models import Model`**: Correct. Do not change.

## Verification

After changes, verify:
- `kaira init` produces a `main.py` that imports `KairaApp`
- `kaira init` produces `requirements.txt` with `khaira>=0.2.3`
- `kaira init` produces `pyproject.toml` with `khaira>=0.2.3`
- Generated `main.py` has no string anchors (`# [ROUTER_REGISTRATION]`, etc.)
- Test pass: `pytest tests/test_commands.py -v`
