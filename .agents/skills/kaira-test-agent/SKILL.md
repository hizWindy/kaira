---
name: kaira-test-agent
description: Updates and adds tests for the Kaira framework migration to ensure KairaApp is the default runtime.
---

# Kaira Test Agent

## Scope

Responsible for Phase 4 of the Kaira framework migration: updating tests and adding integration tests for the new framework behavior.

## Tasks

### 1. Update `tests/test_commands.py`

Add tests for:
- `kaira init` produces `main.py` importing `KairaApp` from `kaira.app`
- Generated `main.py` contains `from kaira.app import KairaApp`
- Generated `main.py` contains `app = KairaApp(...)`
- Generated `requirements.txt` includes `khaira>=0.2.3`
- Generated `pyproject.toml` includes `khaira>=0.2.3`

### 2. Update `tests/test_phase4_wiring.py`

Replace string-marker assertions with `KairaApp` assertions:
- Instead of checking for `# [ROUTER_REGISTRATION]` in `main.py`, check that `KairaApp` has registered routers
- Verify `KairaApp` instance is created correctly

### 3. Add `tests/test_runtime.py` (new file)

Test `KairaApp` initialization and `kaira run` behavior:
```python
def test_kaira_app_default():
    """KairaApp is the default app class for generated projects."""
    ...

def test_kaira_run_uses_kaira_app():
    """kaira run instantiates KairaApp, not fastapi dev."""
    ...
```

### 4. Add Integration Test for `kaira init`

```python
def test_init_creates_kaira_app():
    """kaira init creates a project with KairaApp as the default."""
    result = run("init", "--name", "testproj", "--yes")
    assert "KairaApp" in result.output or check_main_py_has_kaira_app()

def test_init_generates_kaira_dependency():
    """kaira init includes khaira in requirements.txt."""
    result = run("init", "--name", "testproj", "--yes")
    assert "khaira" in read_file("testproj/requirements.txt")
```

### 5. Update Existing Tests That Assert on `main.py` Content

Search for tests that check `main.py` string content and update them:
- `test_phase4_wiring.py` — checks for `# [ROUTER_REGISTRATION]`
- Any test in `test_commands.py` that checks `main.py` content
- Tests in `test_phase4_commands.py`

### 6. Test `run_cmd.py` Without `--framework`

Add a test that verifies `kaira run` works without the `--framework` flag:
```python
def test_run_without_framework_flag():
    """kaira run works without --framework flag."""
    result = run("run", "--help")
    assert "--framework" not in result.output  # removed
```

## Rules

1. **All new tests must use `KairaApp` assertions**, not string-splicing assertions
2. **Do not add tests that depend on `main_app_v3.py.j2`** — it's removed
3. **Test `kaira init` produces the correct generated files** — `main.py`, `requirements.txt`, `pyproject.toml`
4. **Test `kaira run` invokes `KairaApp`** — verify it doesn't call `subprocess.run(["fastapi", ...])`
5. **Run `pytest` after each batch of test changes** to ensure no regressions

## Verification

- `pytest tests/test_commands.py -v` passes
- `pytest tests/test_shortcuts.py -v` passes
- `pytest` (full suite) passes
- New tests cover `KairaApp` initialization, `kaira run`, and generated dependencies
