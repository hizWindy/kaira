# Kaira ⚡ — Project Overview

> **In plain English:** Kaira is a tool that does the boring, repetitive setup work for you — so you can focus on building the actual product.
>
> **In developer terms:** Kaira is a Python-based CLI scaffolding tool that auto-generates a complete FastAPI 5-layer backend pipeline (model → repository → schema → service → router) from a single command using Jinja2 templates.

---

## 📌 Current Status

| | |
|---|---|
| **Name** | Kaira (formerly DevFlow) |
| **Version** | 0.1.0 |
| **CLI command** | `kaira` |
| **Python package** | `kaira` |
| **Project config file** | `.kaira.json` |
| **Command groups registered** | 43 |
| **Test suite** | 264 passed, 1 skipped |
| **Supported Python** | 3.10 → 3.14 (verified installs, wheels-only, no compiler needed) |
| **Default database** | SQLite (zero-config, boots on a fresh clone) |

**In short:** the tool is stable and fully working. The generated projects are now *self-contained* — anyone can clone one from GitHub and run it without having Kaira installed — and the dependency setup installs cleanly across Python 3.10–3.14.

---

## 🆕 Recent Changes

This section records everything changed in the latest round of work, newest concerns first.

### 1. Rebrand: DevFlow → Kaira (top to bottom)
- Brand name, the typed CLI command (`kaira`), and the Python package folder (`kaira/`) all renamed.
- Config file `.devflow.json` → **`.kaira.json`**; internal `DevFlowConfig` → `KairaConfig`.
- Entry point is now `kaira = "kaira.main:app"`; the old `devflow` command is removed.

### 2. Seamless clone-and-run for generated projects
A stranger who clones a Kaira-generated repo can now get it running with no Kaira dependency:
```bash
git clone <repo> && cd project
cp .env.example .env
docker compose up -d db          # skipped entirely on SQLite
pip install -r requirements.txt
alembic upgrade head             # skipped on MongoDB
fastapi dev main.py
```
- **`requirements.txt` added** to every generated project (pinned mirror of `pyproject.toml`) for broad clone/deploy compatibility.
- **Self-contained README** — no longer instructs cloners to run `kaira …`; uses plain `alembic` and the FastAPI CLI, documents venv + Docker + Makefile paths.
- **`Makefile`** added: `make install / db / migrate / dev / run / test`.

### 3. Runs on the official FastAPI CLI
- `kaira run` now uses **`fastapi dev`** (hot-reload) and **`fastapi run`** (production), matching the official `fastapi[standard]` docs, with an automatic fallback to plain `uvicorn` when the CLI is unavailable.

### 4. Virtual-environment awareness
- `kaira init` now **creates a `.venv`** inside the new project and installs dependencies into it.
- Every subprocess command (`run`, `migrate`, `seed`, `test`, `deps`) resolves and targets the **project's `.venv`** (via `get_venv_python()`), not Kaira's own interpreter.

### 5. Database & environment defaults
- **SQLite is the default** — a fresh project boots with **no database server**: its `.env` ships an active `DATABASE_URL` pointing at a local SQLite file.
- **`docker-compose.yml` matches the chosen DB** — emits `postgres` / `mysql` / `mongo` services accordingly, and omits the DB service for SQLite (previously always Postgres).
- **Fewer env files** — `kaira init` now generates only `.env` (active) and `.env.example` (committed template). The old `.env.staging` / `.env.production` files were removed; stage/prod secrets belong in the deploy platform, not committed files.

### 6. Dependency pins fixed for modern Python (installs everywhere)
- Generated projects previously used **exact `==` pins** that had no wheels for newer Python (e.g. `asyncpg==0.30.0` failed to build on Python 3.14).
- Now they use **minimum `>=` pins**, so pip installs the newest wheel that fits the user's Python — with upper caps only where a next major would break generated code:
  - `beanie<2.0` (2.0 drops Motor, which the Mongo template uses)
  - `motor<4.0`, `bcrypt<5.0` (5.0 trips a passlib warning)
  - `sqlalchemy<3.0`, `pydantic<3.0` (prudent guards)
- Verified: Postgres, MySQL, MongoDB, and SQLite dependency sets all install cleanly on Python 3.14 with `pip check` reporting no conflicts.

---

## 🤔 What Problem Does It Solve?

### For everyone
Every time a developer builds a web application backend, they have to write the same types of files over and over again — files that handle data, files that talk to the database, files that validate input, and files that expose the API. This is tedious, slow, and error-prone.

**Kaira automates all of that.**

### For developers
Manually writing boilerplate for every new model (SQLAlchemy ORM, Pydantic schemas, FastAPI routers, service layer, repository pattern) is repetitive and inconsistent across team members. Kaira enforces a consistent 5-layer architecture and generates all layers from a single model definition.

---

## ⚡ What It Does — One Command, Five Files

### For everyone
Imagine you're building an app and you need a "User" feature — the ability to create, read, update, and delete users. Normally a developer would spend hours writing all the plumbing code. With Kaira, you type one line:

```bash
kaira generate model User --fields "username:str, email:str, age:int"
```

And it instantly creates **5 ready-to-use files**:

| What it creates | What it does (plain English) |
|---|---|
| `models/user.py` | Defines what a User looks like in the database |
| `repositories/user_repository.py` | Handles saving, fetching, updating, and deleting users |
| `schemas/user_schema.py` | Validates data coming in and going out of the API |
| `services/user_service.py` | Contains the business rules and logic |
| `routers/user_router.py` | Exposes the API endpoints (URLs you can call) |

### For developers
A single `kaira generate model <Name> --fields "<definitions>"` call renders all 5 Jinja2 templates with correct typing, SQLAlchemy column mapping, Pydantic v2 models, FastAPI `Depends()` injection, and full CRUD endpoints — in under a second.

---

## 🧰 Full Feature Set

### 🏗️ Project Initialization
**Plain English:** Sets up a brand-new, fully organized project folder — including its own virtual environment and installed dependencies — so you can start coding immediately.

**Developer terms:** Scaffolds a complete FastAPI project directory with `main.py`, `core/database.py`, `core/logger.py`, `middleware/security.py`, `.env` + `.env.example`, `requirements.txt`, `pyproject.toml`, `Makefile`, and optional Docker/CI config — driven by an interactive wizard or CLI flags. Creates a `.venv` and installs dependencies into it.

```bash
kaira init                                          # Interactive wizard (SQLite by default)
kaira init myproject --db postgresql --auth jwt    # Non-interactive
kaira init myproject --db mongodb --docker --ci github
```

---

### 🗄️ Database Support
**Plain English:** Whether you're using a classic database or a modern document-based one, Kaira generates the right code for it automatically.

**Developer terms:** Template switching based on `db_type` in `.kaira.json`. Relational databases (SQLite, PostgreSQL, MySQL) use async SQLAlchemy 2.0 with `AsyncSession`. MongoDB uses Motor + Beanie ODM. SQLite is the default and requires no server.

| Database | Technology used | Server needed? |
|---|---|---|
| SQLite (default) | Async SQLAlchemy + aiosqlite | No — file-based, zero-config |
| PostgreSQL | Async SQLAlchemy + asyncpg | Yes (or `docker compose up -d db`) |
| MySQL | Async SQLAlchemy + aiomysql | Yes (or Docker) |
| MongoDB | Motor + Beanie ODM | Yes (or Docker) |

---

### 🗄️ Database Diagnostics & Info
**Plain English:** Inspect your active database connection status, credentials, and list all generated tables/collections instantly.

**Developer terms:** Diagnostic commands for database layer testing. Replaces basic TCP port checks with real authenticated login queries (`SELECT 1` or MongoDB pings), dynamically falls back to SQLite default configuration inside `config/settings.py` if `.env` keys are commented out, and lists tables with column and row counts inside a Rich layout.

* `kaira db connect`: Active credentialed query/login validation (avoids false-positive port checks).
* `kaira db status`: Diagnostic configuration status summary showing active URL schema and login status.
* `kaira db info`: Fetches table listings with **column and row counts** for SQL databases, or collections (and document counts) for MongoDB, formatted as a Rich Table.

---

### 🔐 Authentication Scaffolding
**Plain English:** Adds login/security boilerplate so you don't have to build it from scratch.

**Developer terms:** Generates JWT routes + dependencies + token utilities, OAuth2 flow, or API Key dependency pattern — all wired into the FastAPI app.

| Mode | What you get |
|---|---|
| `jwt` | Login/register routes, token creation, refresh, dependencies |
| `oauth2` | OAuth2 password flow boilerplate |
| `api-key` | API Key header dependency |
| `none` | No auth scaffold |

---

### 🔗 Relationship Management
**Plain English:** Easily connect different parts of your app together (e.g., a Post belongs to a User, a Post has many Comments).

**Developer terms:** Appends SQLAlchemy `relationship()` and `ForeignKey` declarations directly to existing model files.

```bash
kaira add relation Post --has-many Comment --cascade "all, delete-orphan"
kaira add relation Post --has-one User
kaira add relation Post --many-to-many Tag
```

---

### 🔄 Database Migrations
**Plain English:** Keeps your database structure in sync with your code changes — safely and automatically, with zero manual setup.

**Developer terms:** Zero-configuration Alembic wrapper for database migration tasks. Running any migration command (`make`, `run`, `rollback`) on a fresh project will **automatically initialize Alembic** on the fly if missing, using dynamic async database drivers and model packages walk-discovery. Alembic runs against the project's `.venv`.

```bash
kaira migrate make "add users table"    # Auto-scaffolds Alembic if needed & generates blueprint
kaira migrate run                       # Auto-scaffolds Alembic if needed & applies to database
kaira migrate rollback                  # Reverts the last migration step
```

> Generated projects can also run migrations directly with plain `alembic upgrade head` — no Kaira required.

---

### ⚡ Caching & State (`kaira cache`)
**Plain English:** Stores frequently read info in memory using Redis so it loads instantly.

**Developer terms:** Scaffold `core/cache.py` with namespaced redis-backed caching. Only GET routes are cacheable. Authenticatable routes automatically namespace keys by the authenticated user ID.

```bash
kaira cache init
kaira cache add GET /users
kaira cache clear --all
```

---

### ⚡ Background Tasks (`kaira task`)
**Plain English:** Runs long processes in the background (like sending emails or processing files) so your app stays fast.

**Developer terms:** Scaffolds Celery workers, async task retries, beat scheduling, and standard Logging wrapper (blocking PII leakage in task arguments). Flower web interface dashboard included.

```bash
kaira task init
kaira task generate ProcessInvoice --schedule "crontab(minute=0, hour=0)"
kaira task monitor
```

---

### ⚡ Third-Party Integrations (`kaira integrate`)
**Plain English:** Connects your application to standard software providers (like Stripe for payments or SendGrid for emails) in seconds.

**Developer terms:** Templates and installs SDKs for 15 providers across 6 fields. Configs are handled strictly in settings — never hardcoded, with standard try/except error shielding.

```bash
kaira integrate add --provider payment/stripe
kaira integrate list
```

---

### ⚡ API Testing & client generation (`kaira api`)
**Plain English:** Tests your endpoints, creates Postman collections, and generates code clients for your frontend (Web/Mobile).

**Developer terms:** Validates OpenAPI spec, exports JSON/YAML models, and compiles fully typed TypeScript/JavaScript fetch clients.

```bash
kaira api validate
kaira api client --lang typescript
```

---

### ⚡ Profiling & Loadtesting (`kaira profile` & `kaira loadtest`)
**Plain English:** Measures how fast your URLs respond, and runs stress-testing simulation packages to check how many users your app can handle.

**Developer terms:** Measures response latency distribution (p50/p95/p99) and runs bounded concurrent requests. Prevents accidental targeting of production servers with host locks.

```bash
kaira profile run GET /users
kaira loadtest run GET /users --allow-remote
```

---

### ⚡ Scaffolding Layers (`kaira middleware`, `kaira event`, `kaira flags`, `kaira health-endpoint`, `kaira notify`)
**Plain English:** Sets up standard backend utility files like feature flag toggles, lifespan lifecycle hooks, custom request middleware, and a health monitoring URL.

**Developer terms:** Generates custom Starlette middlewares (protecting core security headers), unauthenticated rate-limited `/health` route, and namespaced feature flags.

```bash
kaira health-endpoint generate
kaira flags add beta_feature --default false
```

---

### ⚡ Server Runner (`kaira run`)
**Plain English:** Starts your app's web server with one command — in fast dev mode with auto-reload, or in production mode.

**Developer terms:** Wraps the official **FastAPI CLI** — `fastapi dev` (hot-reload) and `fastapi run` (production) — auto-detecting the entry file and running it inside the project's `.venv`. Falls back to `uvicorn` (with reload-loop exclusions) when the FastAPI CLI is unavailable.

```bash
kaira run                 # dev mode, hot-reload
kaira run --prod          # production mode
kaira run --port 9000 --host 0.0.0.0
```

---

### ⚡ Deployment Configs (`kaira deploy`)
**Plain English:** Checks your app's readiness checklist and automatically writes configuration scripts for modern hosting platforms.

**Developer terms:** Performs readiness audits and scaffolds configuration files for Render, Railway, Fly.io, and VPS.

```bash
kaira deploy checklist
kaira deploy generate --platform railway
```

---

### 🛡️ Security & Middleware
**Plain English:** Automatically adds security protections to your app — blocking suspicious requests, logging activity, and preventing overload.

**Developer terms:** Generates `middleware/security.py` with CORS configuration, custom security headers, SlowAPI rate limiting, global exception handlers, and structured request logging.

---

### 📋 Built-in Guides
**Plain English:** Has a built-in help system with real, copy-pasteable examples for every feature.

**Developer terms:** `kaira guide [topic]` renders Rich-styled panels with 23 topic guides covering init, generate, db, auth, docker, ci, migrate, config, relations, seed, test, cache, task, integrate, api, quality, deploy, flags, health-endpoint, cloud, fallback, and menu.

```bash
kaira guide          # Show all topics
kaira guide cache    # Guide for Redis caching
kaira guide cloud    # Guide for cloud DB connectivity
```

---

### 🤖 AI-Powered Documentation
**Plain English:** Uses AI to automatically write API documentation for your project.

**Developer terms:** Calls OpenAI or Anthropic APIs via `httpx` to generate structured Markdown API docs per model.

---

### 🐳 Docker & CI/CD
**Plain English:** Prepares your app to be deployed and automates the testing/deployment pipeline setup.

**Developer terms:** Generates `Dockerfile`, a DB-aware `docker-compose.yml` (Postgres/MySQL/Mongo, or none for SQLite), `.dockerignore`, and GitHub Actions / GitLab CI / Bitbucket Pipelines YAML files.

---

### 🌱 Database Seeding
**Plain English:** Fills your database with sample data for testing — without writing it manually.

**Developer terms:** Generates and runs a seed script using SQLAlchemy sessions with Faker-backed random data generation, executed inside the project's `.venv`.

---

### 🔍 Change Detection & Diff
**Plain English:** Before overwriting any files, Kaira shows you exactly what will change — so you never lose your custom code by accident. Supports interactive terminal selection.

**Developer terms:** `kaira check` performs a dry-run conflict detection. `kaira diff <Model>` outputs a unified colored diff. Prompts allow choosing actions using shell arrow keys.

---

### 🧪 Test Generation
**Plain English:** Automatically writes test files for your code, so you can verify everything works correctly.

**Developer terms:** Generates pytest fixtures, conftest, service unit tests, repository tests, and router integration tests via Jinja2 templates.

---

### 🏥 Health & Audit
**Plain English:** Scans your project for problems, missing files, or security issues and reports them in a clear summary. Includes command history audits and config snapshots.

**Developer terms:** `kaira health` validates project layer completeness with structured tables, side-by-side score panels, and recommended actions cards. `kaira audit routes` parses endpoints. `kaira audit security` checks for auth guards and rate limits. `kaira status` monitors configs. `kaira recap show` reads command histories.

---

### ☁️ Cloud & Fallback Resilience
**Plain English:** Connect to modern cloud databases and build offline-resilient apps that fall back to local database storage during cloud outages.

**Developer terms:** Scaffolds Firestore templates (model/repository/schema/service/router). Connects to Supabase, Atlas, or Firebase. Generates a client-side `fallback.py` orchestrating mode transitions (CLOUD ↔ DEGRADED ↔ RECOVERED) via local write queues (`0600` permissions) and automated idempotent replays.

```bash
kaira cloud connect                     # Run cloud wizard
kaira cloud status                      # View latency and state
kaira cloud fallback status             # View local fallback queue size
```

---

### 🔁 Model Sync (`kaira sync`)
**Plain English:** Change a model's fields once, and Kaira updates every layer that uses it.

**Developer terms:** Cascades model field changes across all 5 generated layers so the model, repository, schema, service, and router stay consistent.

---

### ⚡ Interactive Command Palette (`kaira menu`)
**Plain English:** Don't worry about memorising commands — open an interactive keyboard menu to search and run any CLI command.

**Developer terms:** Opens an interactive fuzzy-searchable prompt wrapping all verified CLI commands. Displays shortcut references (Enter to run, Esc to exit) and prints the raw CLI command before running it.

```bash
kaira menu
```

---

## 🛠 Technology Stack

| Component | Library | Why |
|---|---|---|
| CLI framework | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Beautiful, typed CLI with rich terminal output |
| Templating engine | [Jinja2](https://jinja.palletsprojects.com/) | Flexible, powerful code generation |
| ORM | [SQLAlchemy 2.x](https://docs.sqlalchemy.org/en/20/) | Industry-standard Python database toolkit |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) | Fast, modern data validation |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) (`fastapi[standard]`) | High-performance async API framework + official CLI |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) | Database schema versioning |
| Logging | [Loguru](https://github.com/Delgan/loguru) | Simple, structured logging |
| Caching | [Redis](https://redis.io/) | In-memory key-value database for fast response caching |
| Background Jobs | [Celery](https://docs.celeryq.dev/) | Distributed task queue for asynchronous processing |
| Job Dashboard | [Flower](https://flower.readthedocs.io/) | Real-time monitoring and administration tool for Celery |
| Interactive Prompts | [InquirerPy](https://inquirerpy.readthedocs.io/) | Keyboard-driven interactive CLI prompts with custom styling |
| Legacy Prompts | [Questionary](https://questionary.readthedocs.io/) | Fallback terminal prompt wizard |
| Fuzzy Matching | [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) | Fast string matching for CLI suggestions |
| AI Docs | OpenAI / Anthropic via [httpx](https://www.python-httpx.org/) | Intelligent documentation generation |

> **Dependency strategy:** generated projects use minimum-version (`>=`) pins with safety caps, so `pip install` always resolves wheels compatible with the user's Python (3.10–3.14) without needing a C compiler.

---

## 👥 Who Is Kaira For?

| Audience | How Kaira helps |
|---|---|
| **Solo developers** | Skip boilerplate, ship features faster |
| **Small teams** | Enforce consistent architecture across the codebase |
| **Beginners** | Get a correct, best-practice FastAPI structure without knowing all the patterns |
| **Experienced devs** | Stop writing the same code for the 100th time |
| **Open-source authors** | Ship a repo others can clone and run seamlessly — no Kaira required |

---

## 📦 Requirements & Install

- Python 3.10 or newer (works through 3.14)
- pip (Python package manager)

```bash
# Install Kaira (editable/development install)
pip install -e .

# Verify
kaira --version
kaira --help
```

A project generated by Kaira needs only Python 3.10+ (and Docker if you don't use SQLite) — it does **not** require Kaira to be installed to run.

---

*Built with ❤️ to make FastAPI development faster, consistent, and enjoyable.*
