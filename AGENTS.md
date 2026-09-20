# AGENTS.md — Kaira Engine Guidelines

> **Target Audience:** AI Coding Assistants (Antigravity, Claude Code, Cursor, Copilot) & Contributors working directly on the Kaira CLI engine codebase.
>
> **Parent workspace:** See [scripts/AGENTS.md](../AGENTS.md) for unified rules covering both **db** and **kaira** projects.

---

## 1. Project Overview & Mission

**Kaira** (formerly DevFlow) is an automated FastAPI scaffolding CLI that generates clean, production-grade 5-layer backend pipelines from simple model definitions, schemas, and CLI commands.

* **Primary language:** Python 3.10+
* **CLI Framework:** [Typer](https://typer.tiangolo.com/) + [Click](https://click.palletsprojects.com/)
* **Terminal UI:** [Rich](https://rich.readthedocs.io/) + [InquirerPy](https://inquirerpy.readthedocs.io/)
* **Templating Engine:** [Jinja2](https://jinja.palletsprojects.com/)
* **Target Output Stack:** FastAPI, SQLAlchemy 2.0 (Async) / Beanie (MongoDB), Pydantic v2, Alembic, Docker, Pytest.
* **Sibling project:** [db](https://github.com/hizWindy/db) — single-entry-point database management CLI

---

## 1. Project Overview & Mission

**Kaira** (formerly DevFlow) is an automated FastAPI scaffolding CLI that generates clean, production-grade 5-layer backend pipelines from simple model definitions, schemas, and CLI commands.

* **Primary language:** Python 3.10+
* **CLI Framework:** [Typer](https://typer.tiangolo.com/) + [Click](https://click.palletsprojects.com/)
* **Terminal UI:** [Rich](https://rich.readthedocs.io/) + [InquirerPy](https://inquirerpy.readthedocs.io/)
* **Templating Engine:** [Jinja2](https://jinja.palletsprojects.com/)
* **Target Output Stack:** FastAPI, SQLAlchemy 2.0 (Async) / Beanie (MongoDB), Pydantic v2, Alembic, Docker, Pytest.

---

## 2. Repository Layout

```text
.
├── kaira/
│   ├── main.py              # Application entrypoint & command registration
│   ├── config.py            # Global settings, KairaConfig, supported field types
│   ├── console.py           # Rich console singleton
│   ├── commands/            # Modular command handlers (50+ commands, e.g. project, generate, etc.)
│   ├── core/                # Core engines: generator, theme, prompts, aliases, ports, ui
│   └── templates/           # Jinja2 templates for all generated code (*.j2)
├── tests/                   # Pytest test suites (split by phase and feature)
├── .kaira.json              # Local configuration state
├── pyproject.toml           # Package metadata, dependencies, tool configs (ruff, mypy, pytest)
└── CHANGELOG.md             # Historical record of changes & phase releases
```

---

## 3. Strict Architectural Invariants

Whenever you modify or extend Kaira, you **MUST** adhere to the following rules:

### A. The 5-Layer Pipeline
Generated code must strictly maintain separation of concerns:
1. **Model (`models/`)**: SQLAlchemy ORM (or Beanie ODM) mapped classes. Pure data schema.
2. **Repository (`repositories/`)**: Database access layer. Handles queries, filtering, commits. No business logic; raises database/internal exceptions, never HTTP exceptions.
3. **Schema (`schemas/`)**: Pydantic v2 data transfer objects (`Base`, `Create`, `Update`, `Response`). Pure validation and serialization.
4. **Service (`services/`)**: Business logic, cross-model coordination, domain validation. Raises `HTTPException` on logical or client failures.
5. **Router (`routers/`)**: FastAPI path operations (`@router.get`, `@router.post`). Handles dependency injection (`Depends`), query parameters, status codes. Delegates all work to the service layer.

### B. Command Shortcuts & Safety Rules
Kaira provides a curated set of high-frequency shortcuts (`g` for `generate model`, `mr` for `migrate run`, etc.):
- **Additive only:** Long-form commands remain canonical everywhere.
- **Safety guarantee:** Destructive commands (`db reset`, `migrate rollback`, `seed clear`, `docker down --volumes`) **MUST NEVER** have shortcuts.
- **Normalized history:** Invocations recorded in `.kaira/history.jsonl` and `kaira recap` must record the canonical long form.

### C. Terminal & Prompt Invariants
- All interactive prompts must route through [kaira.core.prompts](file:///c:/Users/Asus/Documents/scripts/DevFlow/kaira/core/prompts.py).
- **Non-TTY degradation:** When running in CI, automated scripts, or subagents (`stdin` is not a TTY), interactive prompts **must not hang**. They must cleanly fail with a friendly message pointing to the exact flag to pass (e.g. `--yes`, `--db`, etc.).
- Never leak sensitive arguments (passwords, tokens, keys) in echo resolution or command history.

### D. Generator & Template Integrity
- Generated code strings must come from Jinja2 templates in `kaira/templates/`, rendered via `kaira.core.generator`.
- Any new file introduced in `kaira init` must be added to `kaira/commands/project.py` under the appropriate step with `write_with_check()`.
- Updates to model fields or relations must be reflected in `.kaira.json` via `KairaConfig`.

---

## 4. Development & Testing Workflow

### Running Tests
All tests use `pytest`. Make sure tests pass before and after making changes:

```bash
# Run a single test file
pytest tests/test_shortcuts.py -v

# Run command tests
pytest tests/test_commands.py -v

# Run full test suite
pytest
```

### Code Quality & Standards
- Formatter/Linter: `ruff check .` and `ruff format .`
- Type Checker: `mypy kaira`
- Do not add unpinned or unnecessary runtime dependencies.
- Keep comments and docstrings intact when editing existing files.
