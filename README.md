# DevFlow ⚡

**Automated FastAPI scaffolding CLI** — generate complete 5-layer backend pipelines from model definitions.

```
devflow generate model User --fields "username:str, email:str, age:int"
```

In one command, DevFlow generates:

| Layer | File | Description |
|-------|------|-------------|
| Model | `models/user.py` | SQLAlchemy ORM with typed columns |
| Repository | `repositories/user_repository.py` | CRUD data access layer |
| Schema | `schemas/user_schema.py` | Pydantic v2 Base/Create/Update/Response |
| Service | `services/user_service.py` | Business logic with HTTPException handling |
| Router | `routers/user_router.py` | FastAPI endpoints with Depends injection |

---

## Installation

### Requirements

- Python 3.10+
- pip

### Install from source

```bash
# Clone or unzip the project
cd DevFlow

# Install in editable mode — registers the `devflow` command globally
pip install -e .

# Verify installation
devflow --version
devflow --help
```

---

## Quick Start

```bash
# 1. Initialize a new FastAPI project in the current directory
devflow init

# 2. (Optional) Initialize with JWT auth boilerplate
devflow init --with-auth

# 3. Generate a complete 5-layer pipeline
devflow generate model User --fields "username:str, email:str, age:int"

# 4. Generate another model
devflow generate model Post --fields "title:str, body:str, published:bool"

# 5. Add a relationship
devflow add relation Post --has-many Comment --cascade "all, delete-orphan"

# 6. Initialize Alembic and run migrations
devflow migrate init
devflow migrate make "initial migration"
devflow migrate run

# 7. Start the server
uvicorn main:app --reload
```

---

## All Commands

### `devflow init`

Scaffold a full FastAPI project structure:

```
project/
├── main.py           # FastAPI app factory
├── database.py       # SQLAlchemy engine + session + Base
├── models/
├── repositories/
├── schemas/
├── services/
├── routers/
├── tests/
├── docs/
├── alembic/
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
└── .devflow.json     # DevFlow project config
```

```bash
devflow init
devflow init --with-auth    # Adds auth.py with JWT boilerplate
```

---

## Phase 3: Project Wizard, Database Modes, and Security Defaults

Phase 3 expands `devflow init` into a named project scaffold with database-aware templates,
auth boilerplate, Docker/CI options, logging, security middleware, and generated project docs.

```bash
# Interactive wizard
devflow init

# Non-interactive project creation
devflow init myproject --db sqlite --auth jwt --docker --ci github
devflow init myproject --db postgresql --auth none --no-docker --ci none
devflow init myproject --db mongodb --auth api-key --docker --ci gitlab
```

Supported database modes:

| `--db` | Generated database layer |
|--------|---------------------------|
| `sqlite` | Async SQLAlchemy + aiosqlite |
| `postgresql` | Async SQLAlchemy + asyncpg |
| `mysql` | Async SQLAlchemy + aiomysql |
| `mongodb` | Motor + Beanie ODM |

Supported auth modes:

| `--auth` | Generated auth layer |
|----------|----------------------|
| `jwt` | JWT routes, dependencies, schemas, token utilities |
| `oauth2` | OAuth2 boilerplate |
| `api-key` | API-key dependency boilerplate |
| `none` | No auth scaffold |

Phase 3 projects include:

- `core/database.py` selected for the configured database
- `core/logger.py` with Loguru setup
- `middleware/security.py` for CORS, headers, request logging, and exception handlers
- `rate_limit.py` with SlowAPI limiter setup
- `.env`, `.env.development`, `.env.staging`, `.env.production`, and `.env.example`
- generated `pyproject.toml`, `README.md`, `.gitignore`, and optional Docker/CI files

### `devflow guide`

Use the built-in guides for copy-pasteable examples:

```bash
devflow guide
devflow guide init
devflow guide generate
devflow guide db
devflow guide config
```

### Database-aware generation

`devflow generate` reads `.devflow.json` and switches templates based on `db_type`:

- `sqlite`, `postgresql`, `mysql` use SQLAlchemy models plus async repositories.
- `mongodb` uses Beanie document models plus MongoDB repositories.

```bash
devflow config set db_type postgresql
devflow config set auth_type jwt
devflow config set api_version v2
devflow generate model User --fields "username:str, email:str"
```

Routers generated inside a Phase 3 project are registered in `main.py` under the configured API prefix.

---

### `devflow generate`

#### Generate full pipeline

```bash
devflow generate model <ModelName> --fields "<field_definitions>"

# Examples
devflow generate model User --fields "username:str, email:str, age:int"
devflow generate model Product --fields "name:str, price:float, in_stock:bool"
devflow generate model Event --fields "title:str, start_at:datetime, description:Optional[str]"

# Complexity tiers
devflow generate model User --fields "name:str" --tier simple   # model + schema + router only
devflow generate model User --fields "name:str" --tier full     # all 5 layers (default)

# Force overwrite without prompting
devflow generate model User --fields "name:str" --force
```

#### Supported field types

| Type | SQLAlchemy | Python |
|------|-----------|--------|
| `str` | `String` | `str` |
| `int` | `Integer` | `int` |
| `float` | `Float` | `float` |
| `bool` | `Boolean` | `bool` |
| `datetime` | `DateTime` | `datetime` |
| `Optional[str]` | `String(nullable=True)` | `Optional[str]` |
| `Optional[int]` | `Integer(nullable=True)` | `Optional[int]` |
| `Optional[float]` | `Float(nullable=True)` | `Optional[float]` |
| `Optional[bool]` | `Boolean(nullable=True)` | `Optional[bool]` |
| `Optional[datetime]` | `DateTime(nullable=True)` | `Optional[datetime]` |

#### Generate single layers

```bash
devflow generate router User --fields "name:str"
devflow generate service User --fields "name:str"
devflow generate schema User --fields "name:str"
devflow generate repository User --fields "name:str"
```

#### Bulk generation from JSON

```bash
devflow generate bulk models.json
devflow generate bulk models.json --force
```

**models.json format:**

```json
[
  {
    "name": "User",
    "fields": {
      "username": "str",
      "email": "str",
      "age": "int"
    }
  },
  {
    "name": "Post",
    "fields": {
      "title": "str",
      "body": "str"
    },
    "relations": [
      { "type": "many-to-one", "target": "User" }
    ],
    "tier": "full"
  }
]
```

---

### `devflow add`

#### Add relationships

```bash
# One-to-many (Post has many Comments)
devflow add relation Post --has-many Comment --cascade "all, delete-orphan"

# Many-to-one (Post belongs to User)
devflow add relation Post --has-one User

# Many-to-many (Post has many Tags)
devflow add relation Post --many-to-many Tag
```

Appends the relationship code directly to the existing model file.

---

### `devflow migrate`

```bash
devflow migrate make "msg"    # New migration (runs: alembic revision --autogenerate -m "msg")
devflow migrate run           # Apply migrations (runs: alembic upgrade head)
devflow migrate rollback      # Revert last migration (runs: alembic downgrade -1)
devflow migrate init          # Initialize Alembic (runs: alembic init alembic)
```

> **Note:** DevFlow provides a **zero-configuration** migration workflow. You do not need to run `devflow migrate init` or manually configure `alembic/env.py`. Running any migration command (`make`, `run`, or `rollback`) automatically initializes and pre-configures Alembic behind the scenes if it hasn't been set up yet.

---

### `devflow db`

Database verification, diagnostics, and schema/table structure inspection:

```bash
devflow db status             # Display active DB type, connection URL, and login status
devflow db connect            # Perform a real database login check & verification query
devflow db info               # List all tables & column counts (or collections & doc counts)
devflow db shell              # Launch an interactive database shell (psql, mysql, sqlite3)
devflow db backup             # Backup active database to a SQL dump/file
devflow db restore <file>     # Restore active database from a SQL dump/file
devflow db reset              # Drop and recreate the database (destructive)
devflow db switch <type>      # Switch DB type (routes cloud providers to cloud connect)
devflow db benchmark          # Time connection/query latency
```

*(9 commands total.)*

> **Note:** All database commands dynamically resolve the active connection URL from your environment profile (e.g. `.env.development`) and fall back to your default local SQLite configuration if no credentials are provided. Connection URLs and driver error messages are always credential-masked (`user:****@host`).

---

### `devflow sync model`

Cascade a model's field changes across all five layers — the *continuous* half of continuous scaffolding. Add a field once and schema + router regenerate to match; the service layer is flagged (never auto-rewritten):

```bash
devflow sync model User --fields "phone:str, verified:bool"   # add fields inline
devflow sync model User                                       # detect hand-edits to models/user.py
devflow sync model User --dry-run                             # preview the per-layer plan
devflow sync model --all                                      # sync every registered model
```

| Layer | Action |
|---|---|
| Model | Apply field changes (overwrite with confirm) |
| Schema | Regenerate — mirrors model fields |
| Router | Regenerate — re-point schema references |
| Repository | Untouched |
| Service | Flagged for manual review — never auto-rewritten |

> Removed fields require a typed confirmation (never silently dropped). After a relational sync, run `devflow migrate make "sync <model>"`.

---

### `devflow env audit` / `devflow env prune`

Keep `.env` files lean — audit every key against enabled features, then prune the ones for features you never turned on:

```bash
devflow env audit    # table: key · owning feature · referenced in code? · keep/unused
devflow env prune    # remove unused-feature keys from all .env.* files (typed confirm)
```

> Core keys (`DATABASE_URL`, `APP_ENV`, …) and any key referenced in your code are never pruned. `env prune` is blocked when `APP_ENV=production`.

---

### `devflow info`

Show current project configuration and all tracked models:

```bash
devflow info
```

---

### `devflow check`

Show what files would be overwritten without writing anything:

```bash
devflow check
```

---

### `devflow diff`

Show a colored unified diff between existing and freshly generated files:

```bash
devflow diff User
devflow diff User --layer router
devflow diff User --fields "username:str, email:str, bio:Optional[str]"
```

---

### `devflow list`

```bash
devflow list models    # List all files in models/
devflow list routes    # List all router files and their endpoints
```

---

### `devflow docs`

AI-powered documentation generation (requires API key):

```bash
devflow docs generate              # Generate docs for all models → docs/api.md
devflow docs generate User         # Generate docs for one model → docs/User.md
```

**Configure AI provider:**

```bash
devflow config set ai_provider openai      # or: anthropic
devflow config set ai_model gpt-4o
devflow config set ai_api_key_env OPENAI_API_KEY
```

Set your API key in `.env`:

```bash
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

If no API key is set, DevFlow generates a basic Markdown doc without AI.

---

### `devflow config`

```bash
devflow config show                         # Display full config
devflow config get default_tier             # Get a value
devflow config set default_tier simple      # Set a value
devflow config set models_dir app/models    # Change output directories
```

**Settable keys:**

| Key | Default | Description |
|-----|---------|-------------|
| `output_dir` | `.` | Root output directory |
| `models_dir` | `models` | Models directory |
| `repositories_dir` | `repositories` | Repositories directory |
| `schemas_dir` | `schemas` | Schemas directory |
| `services_dir` | `services` | Services directory |
| `routers_dir` | `routers` | Routers directory |
| `default_tier` | `full` | Default complexity tier |
| `ai_provider` | `openai` | AI documentation provider |
| `ai_model` | `gpt-4o` | AI model to use |
| `ai_api_key_env` | `OPENAI_API_KEY` | Env var for API key |

---

## Phase 4 Commands & Features

Phase 4 adds 87 new commands across 14 new functional areas:

### ⚡ Caching (`devflow cache`)
Redis cache management and route caching:
- `devflow cache init` — Scaffold `core/cache.py` and register in settings
- `devflow cache add GET <route> [--ttl 300]` — Add GET route caching
- `devflow cache clear [<route> | --all]` — Clear cached routes
- `devflow cache status` — View Redis status and keys

### ⚡ Background Tasks (`devflow task`)
Scaffold background tasks via Celery:
- `devflow task init` — Scaffolds celery configurations
- `devflow task generate <TaskName> [--schedule "<cron>"]` — Scaffolds background task
- `devflow task list` — List all Celery tasks
- `devflow task run <TaskName>` — Run background task immediately
- `devflow task monitor` — Open Flower dashboard

### ⚡ Third-Party Integrations (`devflow integrate`)
Scaffold 15 integration providers across 6 categories:
- `devflow integrate --provider <category>/<provider>` (e.g. `email/sendgrid`, `payment/stripe`, `storage/s3`, `monitor/sentry`, etc.)
- `devflow integrate list` — View all available integration options

### ⚡ API Inspection & client generation (`devflow api`)
- `devflow api export [--format json|yaml]` — Save OpenAPI spec
- `devflow api validate` — Validate local OpenAPI spec
- `devflow api list` — List all endpoints
- `devflow api test <METHOD> <route>` — Send test request to local server
- `devflow api postman` — Generate Postman collection
- `devflow api client [--lang typescript|javascript]` — Scaffolds client SDK

### ⚡ Profiling & Loadtesting (`devflow profile` & `devflow loadtest`)
- `devflow profile run <METHOD> <route>` — Trace route response latency (p50/p95/p99)
- `devflow profile report` — View last profile run
- `devflow loadtest run <METHOD> <route>` — Perform concurrent load test (localhost-only safety lock)

### ⚡ Deployment Configs (`devflow deploy`)
- `devflow deploy generate --platform <platform>` — Scaffold Render/Railway/Fly/VPS configs
- `devflow deploy checklist` / `devflow deploy check` — Deploy readiness audit
- `devflow deploy run --platform <platform>` — Trigger deployment (requires passing checklist)

### ⚡ Scaffolding Layers (`devflow middleware`, `devflow event`, `devflow flags`, `devflow health-endpoint`)
- `devflow middleware add <MiddlewareName>` — Scaffold Starlette middleware
- `devflow event generate <startup|shutdown>` — Scaffold lifespan hooks
- `devflow flags add <flag_name>` — Scaffold feature flag toggle
- `devflow health-endpoint generate` — Scaffold unauthenticated /health route

---


## Change Detection

DevFlow **never silently overwrites** files. When a file already exists:

```
┌─ File Conflict ──────────────────────────────────────────────────┐
│ ⚠  File already exists: models/user.py                          │
│ Choose an action:                                                 │
│   o — overwrite                                                   │
│   s — skip                                                        │
│   d — show diff                                                   │
└──────────────────────────────────────────────────────────────────┘
Your choice [o/s/d] (s):
```

Use `--force` to bypass prompts and always overwrite.

---

## Project Structure (Generated)

```
my-api/
├── main.py
├── database.py
├── auth.py                         # (--with-auth only)
├── models/
│   ├── __init__.py
│   ├── user.py
│   └── post.py
├── repositories/
│   ├── user_repository.py
│   └── post_repository.py
├── schemas/
│   ├── user_schema.py
│   └── post_schema.py
├── services/
│   ├── user_service.py
│   └── post_service.py
├── routers/
│   ├── user_router.py
│   └── post_router.py
├── tests/
├── docs/
│   └── api.md
├── alembic/
├── .env
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
└── .devflow.json
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/ --cov=devflow --cov-report=term-missing
```

---

## Tech Stack

| Component | Library |
|-----------|---------|
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| Templates | [Jinja2](https://jinja.palletsprojects.com/) |
| ORM | [SQLAlchemy 2.x](https://docs.sqlalchemy.org/en/20/) |
| Schemas | [Pydantic v2](https://docs.pydantic.dev/) |
| API | [FastAPI](https://fastapi.tiangolo.com/) |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) |
| AI Docs | OpenAI / Anthropic (via [httpx](https://www.python-httpx.org/)) |

---

## License

MIT
