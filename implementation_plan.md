# Phase 3 Implementation Plan

## Overview
Phase 3 adds 8 major features to DevFlow without touching any existing Phase 1/2 commands.

---

## Proposed Changes

### Component 1 — `kaira/config.py`

#### [MODIFY] [config.py](file:///c:/Users/msu-wone/Downloads/DevFlow/kaira/config.py)
- Add `db_type: str = "sqlite"` field to `KairaConfig`
- Add `api_version: str = "v1"` field to `KairaConfig`
- Add `auth_type: str = "none"` field to `KairaConfig`

---

### Component 2 — Templates (new database-aware templates)

#### [NEW] `kaira/templates/logger.py.j2`
Loguru logger setup for `core/logger.py` in generated projects.

#### [NEW] `kaira/templates/security_middleware.py.j2`
Security middleware: CORS, headers, rate limit, exception handler, request logging.

#### [NEW] `kaira/templates/database_async.py.j2`
Async SQLAlchemy setup for PostgreSQL / MySQL / SQLite (engine, AsyncSession, get_db).

#### [NEW] `kaira/templates/database_mongodb.py.j2`
Motor + Beanie setup with `init_db()` coroutine.

#### [NEW] `kaira/templates/model_mongodb.py.j2`
Beanie `Document` model instead of SQLAlchemy ORM.

#### [NEW] `kaira/templates/repository_async.py.j2`
Async SQLAlchemy 2.0 repository with `await db.execute(select(...))`.

#### [NEW] `kaira/templates/repository_mongodb.py.j2`
Beanie/Motor async repository.

#### [MODIFY] `kaira/templates/service.py.j2`
Add Loguru logging to every method (info, success, warning, error). Add full Google-style docstrings and type hints. Add try/except on every method. Never log passwords/tokens.

#### [MODIFY] `kaira/templates/router.py.j2`
Add Loguru request logging. Add `/api/v1` prefix registration comment. Add full docstrings.

#### [NEW] `kaira/templates/main_app_v3.py.j2`
Updated `main.py` template with versioned API prefix (`API_V1_PREFIX = "/api/v1"`), security middleware import, logger import.

#### [NEW] `kaira/templates/pyproject_generated.toml.j2`
A `pyproject.toml` for the generated project (not DevFlow itself).

#### [NEW] `kaira/templates/readme_project.md.j2`
A README.md for the generated project.

#### [NEW] `kaira/templates/gitignore_project.j2`
A comprehensive `.gitignore` for generated projects.

---

### Component 3 — New Command Modules

#### [NEW] `kaira/commands/guide_cmd.py`
`kaira guide [topic]` — 11 subguides with Rich-styled panels and copy-pasteable examples.

#### [MODIFY] `kaira/commands/project.py`
- Add `name` argument to `init_command`
- Interactive wizard using `questionary` (or fallback to Typer prompts if not installed)
- DB selection, auth selection, Docker, CI/CD
- Rich-styled package installation display (abstracted pip)
- Create named project folder with full structure
- Generate `core/logger.py`, `core/database.py`, `middleware/security.py`
- Generate DB-appropriate code based on selection
- Auto-detect and skip already-installed packages

---

### Component 4 — `kaira/main.py`

#### [MODIFY] [main.py](file:///c:/Users/msu-wone/Downloads/DevFlow/kaira/main.py)
- Update `cmd_init` to accept optional `name: str` argument and `--db`, `--auth`, `--docker`, `--ci` flags
- Register `guide_app` Typer group

---

### Component 5 — README.md

#### [MODIFY] [README.md](file:///c:/Users/msu-wone/Downloads/DevFlow/README.md)
- Add Phase 3 section with all new commands documented

---

## Key Design Decisions

### Interactive wizard fallback
`questionary` is the preferred library. However, since it may not be installed, we will:
1. Try `import questionary`
2. If unavailable, fall back to `typer.prompt` / `typer.confirm` with plain text menus

### DB-specific template switching
The `generate` command will read `config.db_type` and select the correct model/repository template:
- `sqlite`, `postgresql`, `mysql` → `model.py.j2` + `repository_async.py.j2`
- `mongodb` → `model_mongodb.py.j2` + `repository_mongodb.py.j2`

### API versioning prefix
The `main_app_v3.py.j2` template sets `API_V1_PREFIX = "/api/v1"` (configurable via `config.api_version`). The existing `router.py.j2` already sets a prefix per-resource (e.g. `/users`); the versioned prefix is added at `include_router` time.

### Package installation display
A dedicated `_install_packages()` helper will be added to `project.py`. It uses `subprocess.run` with `stdout=DEVNULL, stderr=PIPE`, then displays results in a Rich Live table.

### Ruff auto-format
After every `kaira generate` call, a `_ruff_format(path)` helper runs `ruff check --fix` and `ruff format` silently. If ruff is not installed, a one-time warning is shown.

---

## Verification Plan

### Automated Tests
- `pytest tests/ -v` — all 137 existing tests must still pass
- New tests in `tests/test_phase3.py`

### Manual
- `kaira guide` → rich guide panel
- `kaira init myproject --db sqlite` → creates `myproject/` with full structure
- `kaira init myproject --db mongodb` → MongoDB-flavored templates
- `kaira generate model User --fields "username:str"` → async service/router with loguru logs
