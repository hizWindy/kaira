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
devflow migrate init          # Initialize Alembic (runs: alembic init alembic)
devflow migrate make "msg"    # New migration (runs: alembic revision --autogenerate -m "msg")
devflow migrate run           # Apply migrations (runs: alembic upgrade head)
devflow migrate rollback      # Revert last migration (runs: alembic downgrade -1)
```

> **Note:** After `devflow migrate init`, edit `alembic/env.py` to import your `Base` and models.

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
