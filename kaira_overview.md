# DevFlow ⚡ — Project Overview

> **In plain English:** DevFlow is a tool that does the boring, repetitive setup work for you — so you can focus on building the actual product.
>
> **In developer terms:** DevFlow is a Python-based CLI scaffolding tool that auto-generates a complete FastAPI 5-layer backend pipeline (model → repository → schema → service → router) from a single command using Jinja2 templates.

---

## 🤔 What Problem Does It Solve?

### For everyone
Every time a developer builds a web application backend, they have to write the same types of files over and over again — files that handle data, files that talk to the database, files that validate input, and files that expose the API. This is tedious, slow, and error-prone.

**DevFlow automates all of that.**

### For developers
Manually writing boilerplate for every new model (SQLAlchemy ORM, Pydantic schemas, FastAPI routers, service layer, repository pattern) is repetitive and inconsistent across team members. DevFlow enforces a consistent 5-layer architecture and generates all layers from a single model definition.

---

## ⚡ What It Does — One Command, Five Files

### For everyone
Imagine you're building an app and you need a "User" feature — the ability to create, read, update, and delete users. Normally a developer would spend hours writing all the plumbing code. With DevFlow, you type one line:

```bash
devflow generate model User --fields "username:str, email:str, age:int"
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
A single `devflow generate model <Name> --fields "<definitions>"` call renders all 5 Jinja2 templates with correct typing, SQLAlchemy column mapping, Pydantic v2 models, FastAPI `Depends()` injection, and full CRUD endpoints — in under a second.

---

## 🧰 Full Feature Set

### 🏗️ Project Initialization
**Plain English:** Sets up a brand-new, fully organized project folder so you don't have to create each folder and starter file manually.

**Developer terms:** Scaffolds a complete FastAPI project directory with `main.py`, `core/database.py`, `core/logger.py`, `middleware/security.py`, `.env` files, and optional Docker/CI config — driven by an interactive wizard or CLI flags.

```bash
devflow init                                          # Interactive wizard
devflow init myproject --db postgresql --auth jwt    # Non-interactive
devflow init myproject --db mongodb --docker --ci github
```

---

### 🗄️ Database Support
**Plain English:** Whether you're using a classic database or a modern document-based one, DevFlow generates the right code for it automatically.

**Developer terms:** Template switching based on `db_type` in `.devflow.json`. Relational databases (SQLite, PostgreSQL, MySQL) use async SQLAlchemy 2.0 with `AsyncSession`. MongoDB uses Motor + Beanie ODM.

| Database | Technology used |
|---|---|
| SQLite | Async SQLAlchemy + aiosqlite |
| PostgreSQL | Async SQLAlchemy + asyncpg |
| MySQL | Async SQLAlchemy + aiomysql |
| MongoDB | Motor + Beanie ODM |

---

### 🗄️ Database Diagnostics & Info
**Plain English:** Inspect your active database connection status, credentials, and list all generated tables/collections instantly.

**Developer terms:** Diagnostic commands for database layer testing. Replaces basic TCP port checks with real authenticated login queries (`SELECT 1` or MongoDB pings), dynamically falls back to SQLite default configuration inside `config/settings.py` if `.env` keys are commented out, and lists tables and column/document counts inside a Rich layout.

* `devflow db connect`: Active credentialed query/login validation (avoids false-positive port checks).
* `devflow db status`: Diagnostic configuration status summary showing active URL schema and login status.
* `devflow db info`: Fetches table listings (and column counts) for SQL databases, or collections (and document counts) for MongoDB, formatted as a Rich Table.

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
devflow add relation Post --has-many Comment --cascade "all, delete-orphan"
devflow add relation Post --has-one User
devflow add relation Post --many-to-many Tag
```

---

### 🔄 Database Migrations
**Plain English:** Keeps your database structure in sync with your code changes — safely and automatically, with zero manual setup.

**Developer terms:** Zero-configuration Alembic wrapper for database migration tasks. Running any migration command (`make`, `run`, `rollback`) on a fresh project will **automatically initialize Alembic** on the fly if missing, using dynamic async database drivers and model packages walk-discovery.

```bash
devflow migrate make "add users table"    # Auto-scaffolds Alembic if needed & generates blueprint
devflow migrate run                       # Auto-scaffolds Alembic if needed & applies to database
devflow migrate rollback                  # Reverts the last migration step
```

---

### ⚡ Caching & State (`devflow cache`)
**Plain English:** Stores frequently read info in memory using Redis so it loads instantly.

**Developer terms:** Scaffold `core/cache.py` with namespaced redis-backed caching. Only GET routes are cacheable. Authenticatable routes automatically namespace keys by the authenticated user ID.

```bash
devflow cache init
devflow cache add GET /users
devflow cache clear --all
```

---

### ⚡ Background Tasks (`devflow task`)
**Plain English:** Runs long processes in the background (like sending emails or processing files) so your app stays fast.

**Developer terms:** Scaffolds Celery workers, async task retries, beat scheduling, and standard Logging wrapper (blocking PII leakage in task arguments). Flower web interface dashboard included.

```bash
devflow task init
devflow task generate ProcessInvoice --schedule "crontab(minute=0, hour=0)"
devflow task monitor
```

---

### ⚡ Third-Party Integrations (`devflow integrate`)
**Plain English:** Connects your application to standard software providers (like Stripe for payments or SendGrid for emails) in seconds.

**Developer terms:** Templates and installs SDKs for 15 providers across 6 fields. Configs are handled strictly in settings — never hardcoded, with standard try/except error shielding.

```bash
devflow integrate add --provider payment/stripe
devflow integrate list
```

---

### ⚡ API Testing & client generation (`devflow api`)
**Plain English:** Tests your endpoints, creates Postman collections, and generates code clients for your frontend (Web/Mobile).

**Developer terms:** Validates OpenAPI spec, exports JSON/YAML models, and compiles fully typed TypeScript/JavaScript fetch clients.

```bash
devflow api validate
devflow api client --lang typescript
```

---

### ⚡ Profiling & Loadtesting (`devflow profile` & `devflow loadtest`)
**Plain English:** Measures how fast your URLs respond, and runs stress-testing simulation packages to check how many users your app can handle.

**Developer terms:** Measures response latency distribution (p50/p95/p99) and runs bounded concurrent requests. Prevents accidental targeting of production servers with host locks.

```bash
devflow profile run GET /users
devflow loadtest run GET /users --allow-remote
```

---

### ⚡ Scaffolding Layers (`devflow middleware`, `devflow event`, `devflow flags`, `devflow health-endpoint`, `devflow notify`)
**Plain English:** Sets up standard backend utility files like feature flag toggles, lifespan lifecycle hooks, custom request middleware, and a health monitoring URL.

**Developer terms:** Generates custom Starlette middlewares (protecting core security headers), unauthenticated rate-limited `/health` route, and namespaced feature flags.

```bash
devflow health-endpoint generate
devflow flags add beta_feature --default false
```

---

### ⚡ Deployment Configs (`devflow deploy`)
**Plain English:** Checks your app's readiness checklist and automatically writes configuration scripts for modern hosting platforms.

**Developer terms:** Performs readiness audits and scaffolds configuration files for Render, Railway, Fly.io, and VPS.

```bash
devflow deploy checklist
devflow deploy generate --platform railway
```

---

### 🛡️ Security & Middleware
**Plain English:** Automatically adds security protections to your app — blocking suspicious requests, logging activity, and preventing overload.

**Developer terms:** Generates `middleware/security.py` with CORS configuration, custom security headers, SlowAPI rate limiting, global exception handlers, and structured request logging.

---

### 📋 Built-in Guides
**Plain English:** Has a built-in help system with real, copy-pasteable examples for every feature.

**Developer terms:** `devflow guide [topic]` renders Rich-styled panels with 23 topic guides covering init, generate, db, auth, docker, ci, migrate, config, relations, seed, test, cache, task, integrate, api, quality, deploy, flags, health-endpoint, cloud, fallback, and menu.

```bash
devflow guide          # Show all topics
devflow guide cache    # Guide for Redis caching
devflow guide cloud    # Guide for cloud DB connectivity
```

---

### 🤖 AI-Powered Documentation
**Plain English:** Uses AI (like ChatGPT) to automatically write API documentation for your project.

**Developer terms:** Calls OpenAI or Anthropic APIs via `httpx` to generate structured Markdown API docs per model.

---

### 🐳 Docker & CI/CD
**Plain English:** Prepares your app to be deployed and automates the testing/deployment pipeline setup.

**Developer terms:** Generates `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and GitHub Actions / GitLab CI / Bitbucket Pipelines YAML files.

---

### 🌱 Database Seeding
**Plain English:** Fills your database with sample data for testing — without writing it manually.

**Developer terms:** Generates and runs a seed script using SQLAlchemy sessions with Faker-backed random data generation.

---

### 🔍 Change Detection & Diff
**Plain English:** Before overwriting any files, DevFlow shows you exactly what will change — so you never lose your custom code by accident. Supports interactive terminal selection.

**Developer terms:** `devflow check` performs a dry-run conflict detection. `devflow diff <Model>` outputs a unified colored diff. Prompts allow choosing actions using shell arrow keys.

---

### 🧪 Test Generation
**Plain English:** Automatically writes test files for your code, so you can verify everything works correctly.

**Developer terms:** Generates pytest fixtures, conftest, service unit tests, repository tests, and router integration tests via Jinja2 templates.

---

### 🏥 Health & Audit
**Plain English:** Scans your project for problems, missing files, or security issues and reports them in a clear summary. Includes command history audits and config snapshots.

**Developer terms:** `devflow health` validates project layer completeness with structured `SIMPLE_HEAD` tables, side-by-side score panels, and recommended actions cards. `devflow audit routes` parses endpoints. `devflow audit security` checks for auth guards and rate limits. `devflow status` monitors configs. `devflow recap show` reads command histories.

---

### ☁️ Cloud & Fallback Resilience
**Plain English:** Connect to modern cloud databases and build offline-resilient apps that fall back to local database storage during cloud outages.

**Developer terms:** Scaffolds Firestore templates (model/repository/schema/service/router). Connects to Supabase, Atlas, or Firebase. Generates a client-side `fallback.py` orchestrating mode transitions (CLOUD ↔ DEGRADED ↔ RECOVERED) via local write queues (`0600` permissions) and automated idempotent replays.

```bash
devflow cloud connect                     # Run cloud wizard
devflow cloud status                      # View latency and state
devflow cloud fallback status             # View local fallback queue size
```

### ⚡ Interactive Command Palette (`devflow menu`)
**Plain English:** Don't worry about memorising commands — open an interactive keyboard menu to search and run any CLI command.

**Developer terms:** Opens an interactive fuzzy-searchable prompt wrapping all verified CLI commands. Displays shortcut references (Enter to run, Esc to exit) and prints the raw CLI command before running it.

```bash
devflow menu
```

---

## 🛠 Technology Stack

| Component | Library | Why |
|---|---|---|
| CLI framework | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Beautiful, typed CLI with rich terminal output |
| Templating engine | [Jinja2](https://jinja.palletsprojects.com/) | Flexible, powerful code generation |
| ORM | [SQLAlchemy 2.x](https://docs.sqlalchemy.org/en/20/) | Industry-standard Python database toolkit |
| Data validation | [Pydantic v2](https://docs.pydantic.dev/) | Fast, modern data validation |
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) | High-performance async API framework |
| Migrations | [Alembic](https://alembic.sqlalchemy.org/) | Database schema versioning |
| Logging | [Loguru](https://github.com/Delgan/loguru) | Simple, structured logging |
| Caching | [Redis](https://redis.io/) | In-memory key-value database for fast response caching |
| Background Jobs | [Celery](https://docs.celeryq.dev/) | Distributed task queue for asynchronous processing |
| Job Dashboard | [Flower](https://flower.readthedocs.io/) | Real-time monitoring and administration tool for Celery |
| Interactive Prompts | [InquirerPy](https://inquirerpy.readthedocs.io/) | Premium keyboard-driven interactive CLI prompts with custom styling |
| Legacy Prompts | [Questionary](https://questionary.readthedocs.io/) | Fallback terminal prompt wizard |
| Fuzzy Matching | [RapidFuzz](https://github.com/maxbachmann/RapidFuzz) | Fast string matching and similarity calculations for CLI suggestions |
| AI Docs | OpenAI / Anthropic via [httpx](https://www.python-httpx.org/) | Intelligent documentation generation |

---

## 👥 Who Is DevFlow For?

| Audience | How DevFlow helps |
|---|---|
| **Solo developers** | Skip boilerplate, ship features faster |
| **Small teams** | Enforce consistent architecture across the codebase |
| **Beginners** | Get a correct, best-practice FastAPI structure without knowing all the patterns |
| **Experienced devs** | Stop writing the same code for the 100th time |

---

## 📦 Requirements

- Python 3.10 or newer
- pip (Python package manager)

```bash
# Install DevFlow
pip install -e .

# Verify
devflow --version
devflow --help
```

---

*Built with ❤️ to make FastAPI development faster, consistent, and enjoyable.*
