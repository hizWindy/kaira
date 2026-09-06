# Kaira ⚡

**Automated FastAPI scaffolding CLI** — generate complete 5-layer backend pipelines from model definitions.

```
kaira generate model User --fields "username:str, email:str, age:int"
```

In one command, Kaira generates:

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
cd Kaira

# Install in editable mode — registers the `kaira` command globally
pip install -e .

# Verify installation
kaira --version
kaira --help
```

---

## Quick Start

```bash
# 1. Initialize a new FastAPI project in the current directory
kaira init

# 2. (Optional) Initialize with JWT auth boilerplate
kaira init --with-auth

# 3. Generate a complete 5-layer pipeline
kaira generate model User --fields "username:str, email:str, age:int"

# 4. Generate another model
kaira generate model Post --fields "title:str, body:str, published:bool"

# 5. Add a relationship
kaira add relation Post --has-many Comment --cascade "all, delete-orphan"

# 6. Initialize Alembic and run migrations
kaira migrate init
kaira migrate make "initial migration"
kaira migrate run

# 7. Start the server
uvicorn main:app --reload
```

---

## All Commands

### `kaira init`

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
└── .kaira.json     # Kaira project config
```

```bash
kaira init
kaira init --with-auth    # Adds auth.py with JWT boilerplate
```

---

## Phase 3: Project Wizard, Database Modes, and Security Defaults

Phase 3 expands `kaira init` into a named project scaffold with database-aware templates,
auth boilerplate, Docker/CI options, logging, security middleware, and generated project docs.

```bash
# Interactive wizard
kaira init

# Non-interactive project creation
kaira init myproject --db sqlite --auth jwt --docker --ci github
kaira init myproject --db postgresql --auth none --no-docker --ci none
kaira init myproject --db mongodb --auth api-key --docker --ci gitlab
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

### `kaira guide`

Use the built-in guides for copy-pasteable examples:

```bash
kaira guide
kaira guide init
kaira guide generate
kaira guide db
kaira guide config
kaira guide export
```

### Database-aware generation

`kaira generate` reads `.kaira.json` and switches templates based on `db_type`:

- `sqlite`, `postgresql`, `mysql` use SQLAlchemy models plus async repositories.
- `mongodb` uses Beanie document models plus MongoDB repositories.

```bash
kaira config set db_type postgresql
kaira config set auth_type jwt
kaira config set api_version v2
kaira generate model User --fields "username:str, email:str"
```

Routers generated inside a Phase 3 project are registered in `main.py` under the configured API prefix.

---

### `kaira generate`

#### Generate full pipeline

```bash
kaira generate model <ModelName> --fields "<field_definitions>"

# Examples
kaira generate model User --fields "username:str, email:str, age:int"
kaira generate model Product --fields "name:str, price:float, in_stock:bool"
kaira generate model Event --fields "title:str, start_at:datetime, description:Optional[str]"

# Complexity tiers
kaira generate model User --fields "name:str" --tier simple   # model + schema + router only
kaira generate model User --fields "name:str" --tier full     # all 5 layers (default)

# Force overwrite without prompting
kaira generate model User --fields "name:str" --force
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
kaira generate router User --fields "name:str"
kaira generate service User --fields "name:str"
kaira generate schema User --fields "name:str"
kaira generate repository User --fields "name:str"
```

#### Bulk generation from JSON

```bash
kaira generate bulk models.json
kaira generate bulk models.json --force
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

### `kaira add`

#### Add relationships

```bash
# One-to-many (Post has many Comments)
kaira add relation Post --has-many Comment --cascade "all, delete-orphan"

# Many-to-one (Post belongs to User)
kaira add relation Post --has-one User

# Many-to-many (Post has many Tags)
kaira add relation Post --many-to-many Tag
```

Appends the relationship code directly to the existing model file.

---

### `kaira migrate`

```bash
kaira migrate make "msg"    # New migration (runs: alembic revision --autogenerate -m "msg")
kaira migrate run           # Apply migrations (runs: alembic upgrade head)
kaira migrate rollback      # Revert last migration (runs: alembic downgrade -1)
kaira migrate init          # Initialize Alembic (runs: alembic init alembic)
```

> **Note:** Kaira provides a **zero-configuration** migration workflow. You do not need to run `kaira migrate init` or manually configure `alembic/env.py`. Running any migration command (`make`, `run`, or `rollback`) automatically initializes and pre-configures Alembic behind the scenes if it hasn't been set up yet.

---

### `kaira db`

Database verification, diagnostics, and schema/table structure inspection:

```bash
kaira db create             # Auto-provision the database (detect server, create DB, wire DSN)
kaira db status             # Display active DB type, connection URL, and login status
kaira db connect            # Perform a real database login check & verification query
kaira db info               # List all tables & column counts (or collections & doc counts)
kaira db shell              # Launch an interactive database shell (psql, mysql, sqlite3)
kaira db backup             # Backup active database to a SQL dump/file
kaira db restore <file>     # Restore active database from a SQL dump/file
kaira db reset              # Drop and recreate the database (destructive)
kaira db switch <type>      # Switch DB type (routes cloud providers to cloud connect)
kaira db benchmark          # Time connection/query latency
```

*(10 commands total.)*

> **Note:** All database commands dynamically resolve the active connection URL from your environment profile (e.g. `.env.development`) and fall back to your default local SQLite configuration if no credentials are provided. Connection URLs and driver error messages are always credential-masked (`user:****@host`).

---

### `kaira sync model`

Cascade a model's field changes across all five layers — the *continuous* half of continuous scaffolding. Add a field once and schema + router regenerate to match; the service layer is flagged (never auto-rewritten):

```bash
kaira sync model User --fields "phone:str, verified:bool"   # add fields inline
kaira sync model User                                       # detect hand-edits to models/user.py
kaira sync model User --dry-run                             # preview the per-layer plan
kaira sync model --all                                      # sync every registered model
```

| Layer | Action |
|---|---|
| Model | Apply field changes (overwrite with confirm) |
| Schema | Regenerate — mirrors model fields |
| Router | Regenerate — re-point schema references |
| Repository | Untouched |
| Service | Flagged for manual review — never auto-rewritten |

> Removed fields require a typed confirmation (never silently dropped). After a relational sync, run `kaira migrate make "sync <model>"`.

---

### `kaira env audit` / `kaira env prune`

Keep `.env` files lean — audit every key against enabled features, then prune the ones for features you never turned on:

```bash
kaira env audit    # table: key · owning feature · referenced in code? · keep/unused
kaira env prune    # remove unused-feature keys from all .env.* files (typed confirm)
```

> Core keys (`DATABASE_URL`, `APP_ENV`, …) and any key referenced in your code are never pruned. `env prune` is blocked when `APP_ENV=production`.

---

### `kaira info`

Show current project configuration and all tracked models:

```bash
kaira info
```

---

### `kaira check`

Show what files would be overwritten without writing anything:

```bash
kaira check
```

---

### `kaira diff`

Show a colored unified diff between existing and freshly generated files:

```bash
kaira diff User
kaira diff User --layer router
kaira diff User --fields "username:str, email:str, bio:Optional[str]"
```

---

### `kaira list`

```bash
kaira list models    # List all files in models/
kaira list routes    # List all router files and their endpoints
```

---

### `kaira docs`

AI-powered documentation generation (requires API key):

```bash
kaira docs generate              # Generate docs for all models → docs/api.md
kaira docs generate User         # Generate docs for one model → docs/User.md
```

**Configure AI provider:**

```bash
kaira config set ai_provider openai      # or: anthropic
kaira config set ai_model gpt-4o
kaira config set ai_api_key_env OPENAI_API_KEY
```

Set your API key in `.env`:

```bash
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

If no API key is set, Kaira generates a basic Markdown doc without AI.

---

### `kaira config`

```bash
kaira config show                         # Display full config
kaira config get default_tier             # Get a value
kaira config set default_tier simple      # Set a value
kaira config set models_dir app/models    # Change output directories
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
| `db_type` | `sqlite` | Database engine (`postgresql`/`mysql`/`mongodb`/`sqlite`) |
| `api_version` | `v1` | API version prefix |
| `auth_type` | `none` | Auth scaffold (`jwt`/`oauth2`/`api-key`/`none`) |
| `db_name` | `""` | Sanitized database identifier (set by provisioning, Phase 6) |
| `db_provisioned` | `false` | Whether the database has been created/confirmed (Phase 6) |
| `db_mode` | `online` | Resolved bind mode: `online`/`offline`/`auto` (Phase 6) |

The last three fields are written by auto-provisioning (`kaira init` / `kaira db create`) and read by every mode-reporting surface — you normally don't set them by hand.

---

## Phase 4 Commands & Features

Phase 4 adds 87 new commands across 14 new functional areas:

### ⚡ Caching (`kaira cache`)
Redis cache management and route caching:
- `kaira cache init` — Scaffold `core/cache.py` and register in settings
- `kaira cache add GET <route> [--ttl 300]` — Add GET route caching
- `kaira cache clear [<route> | --all]` — Clear cached routes
- `kaira cache status` — View Redis status and keys

### ⚡ Background Tasks (`kaira task`)
Scaffold background tasks via Celery:
- `kaira task init` — Scaffolds celery configurations
- `kaira task generate <TaskName> [--schedule "<cron>"]` — Scaffolds background task
- `kaira task list` — List all Celery tasks
- `kaira task run <TaskName>` — Run background task immediately
- `kaira task monitor` — Open Flower dashboard

### ⚡ Third-Party Integrations (`kaira integrate`)
Scaffold 15 integration providers across 6 categories:
- `kaira integrate --provider <category>/<provider>` (e.g. `email/sendgrid`, `payment/stripe`, `storage/s3`, `monitor/sentry`, etc.)
- `kaira integrate list` — View all available integration options

### ⚡ API Inspection & client generation (`kaira api`)
- `kaira api export [--format json|yaml]` — Save OpenAPI spec
- `kaira api validate` — Validate local OpenAPI spec
- `kaira api list` — List all endpoints
- `kaira api test <METHOD> <route>` — Send test request to local server
- `kaira api postman` — Generate Postman collection
- `kaira api client [--lang typescript|javascript]` — Scaffolds client SDK

### ⚡ Profiling & Loadtesting (`kaira profile` & `kaira loadtest`)
- `kaira profile run <METHOD> <route>` — Trace route response latency (p50/p95/p99)
- `kaira profile report` — View last profile run
- `kaira loadtest run <METHOD> <route>` — Perform concurrent load test (localhost-only safety lock)

### ⚡ Deployment Configs (`kaira deploy`)
- `kaira deploy generate --platform <platform>` — Scaffold Render/Railway/Fly/VPS configs
- `kaira deploy checklist` / `kaira deploy check` — Deploy readiness audit
- `kaira deploy run --platform <platform>` — Trigger deployment (requires passing checklist)

### ⚡ Scaffolding Layers (`kaira middleware`, `kaira event`, `kaira flags`, `kaira health-endpoint`)
- `kaira middleware add <MiddlewareName>` — Scaffold Starlette middleware
- `kaira event generate <startup|shutdown>` — Scaffold lifespan hooks
- `kaira flags add <flag_name>` — Scaffold feature flag toggle
- `kaira health-endpoint generate` — Scaffold unauthenticated /health route

---

## Docker (`kaira docker`)

Docker configuration is **reactive to project state**. The compose services and
the Dockerfile's system build dependencies are rendered from `.kaira.json`, so
enabling a subsystem changes what Docker generates — no hand-editing, no
re-running `init` and losing your setup.

| Project state | Docker reacts |
| --- | --- |
| `db_type: postgresql` / `supabase` | Builder stage gets `gcc libpq-dev` |
| `db_type: mysql` | Builder stage gets `gcc default-libmysqlclient-dev pkg-config` |
| `db_type: mongodb` / `atlas` / `sqlite` / `firebase` | No system build deps at all — the `apt-get` layer is omitted |
| `db_type: postgresql` / `mysql` / `mongodb` | Compose gets a database service with a healthcheck and a named volume |
| `db_type: sqlite` / `supabase` / `atlas` / `firebase` | No database service — file-based or cloud-hosted |
| `cache_enabled: true` | Compose gets Redis with a healthcheck |
| `task_enabled: true` | Compose gets a Celery worker plus the Redis broker |
| `search_provider: elasticsearch` / `meilisearch` | Compose gets that search engine with a healthcheck and volume |
| Any integration SDK | Lands in `requirements.txt` — pip installs it during build, no Dockerfile change |

### Commands

```bash
# Scaffold
kaira docker init --with-compose --python 3.12   # --python accepts 3.10–3.13
kaira docker sync                                # regenerate from current state
kaira docker sync --dry-run                      # show the diff, write nothing

# Build and run a single container
kaira docker build --tag myapp                   # spinner, image size, smart errors
kaira docker build --verbose                     # full Docker output
kaira docker run --tag myapp                     # --init, --read-only, no-new-privileges

# Compose lifecycle
kaira docker up                                  # dev stack + .env.development
kaira docker up --prod --build                   # prod stack (typed confirmation)
kaira docker down                                # stop containers, remove network
kaira docker down --volumes                      # also destroy data (typed confirm)
kaira docker status                              # health, ports, image + volume size

# Security
kaira docker scan --fix                          # exits 1 on HIGH/CRITICAL
```

`kaira docker up` picks the right compose file and env file for the environment;
`kaira docker scan` auto-detects `docker scout`, `trivy`, or `grype` (in that
order), renders a severity-sorted table, and scans local images only unless you
pass `--remote`.

### Staying in sync

Commands that change project state — `cache init`, `task init`, `integrate`,
`db switch`, `cloud connect` — offer to regenerate the Docker files when they
detect drift. Pass `--quiet` to skip the prompt in CI; you then run
`kaira docker sync` yourself.

### What the generated Dockerfile guarantees

Multi-stage build; base image pinned to a full patch version; `--user` pip
install copied into the runtime stage; `--no-install-recommends` with
same-layer apt cleanup; `--no-cache-dir` on pip; dependency manifest copied
before source for layer caching; non-root `addgroup --system` user; in-image
`HEALTHCHECK` using stdlib `urllib` (so `curl` is never installed); exec-form
`CMD`; `EXPOSE` as a documentation contract; and a comprehensive
`.dockerignore` that keeps `.env` out while explicitly allowing `.env.example`.

Production compose adds `read_only`, a size-capped `tmpfs`, `no-new-privileges`,
`json-file` log rotation, resource limits, and keeps database, cache, and search
ports off the host.

---

## Phase 6: Auto DB Provisioning, `run` Overhaul & Offline/Online Engine

### Auto database provisioning

`kaira init` no longer stops at scaffolding — it provisions the actual database. It detects a local database **server** (never a GUI client like pgAdmin/Compass), creates a database named after the project, and wires the DSN into `.env.development`:

```bash
kaira init proj9 --db postgresql        # provision as part of init
kaira db create                         # standalone: provision for current project
kaira db create --name customdb         # override the derived name
kaira db create --skip                  # scaffold the DSN only, don't touch the server
```

- **Passwordless-first.** Trust/socket/env auth connects with no prompt. Only if the server rejects auth are you asked for a password — masked, retried up to 3×, blank = skip.
- **Secrets stay put.** An entered password is written **only** to `.env.development` (git-ignored) and masked in every printed connection string and driver error.
- **Always completes.** No server reachable, or you skip the password? Kaira falls back to offline SQLite at `./.kaira/offline.db` and records `DB_MODE=offline` — explicitly, never silently.
- **Profiles.** `--profile solo` (default) auto-creates; `standard` confirms first; `scale` never auto-creates (managed DB assumed).
- Project names are sanitized to valid DB identifiers (validated against `^[a-z_][a-z0-9_]*$` before any DDL) and stored as `db_name`.

### Offline / Online engine (Layer 1)

The app binds exactly **one** database at startup, governed by two independent dials:

- `DB_MODE` = `online` (default) · `offline` · `auto` — which database binds. Default is **online** on purpose: a transient blip must never silently divert writes onto a throwaway database. Opt into `auto` for a dev-time swap.
- `FALLBACK_MODE` = `off` (default) — runtime resilience (Layers 2/3) is specified but **not built** this release.

**Which DB am I on?** Reported identically on five surfaces from one resolved value — `kaira run` banner, `GET /health` (`database` block, no DSN), the `X-Kaira-DB-Mode` response header, `kaira status`, and the welcome dashboard. The offline store matches your data model: SQLite for relational, a local MongoDB namespace for Mongo (never SQLite).

### Cleaner `kaira run`

- SQL echo is **off by default** — `kaira run --sql` (or `--verbose`) surfaces it for a single run.
- A Loguru `InterceptHandler` unifies uvicorn + SQLAlchemy logging into one format and sink.
- The launch banner shows the database engine, name, and online/offline mode.
See `kaira guide db-provision` and `kaira guide offline` for full walkthroughs.

---

## Phase 7: Data Export (`kaira export`)

Getting data **out** — for you at the terminal, and for the users of the app you scaffolded. Two trust boundaries, one serialization pipeline in `core/export.py`, so neither side can end up with a weaker rule than the other.

### `kaira export data` — your own pull (CLI)

```bash
kaira export data User --format xlsx
kaira export data User --format pdf --limit 500
kaira export data User --format docx --fields "username,email,created_at"
kaira export data User --format xlsx --filter "status:active,role:admin"
kaira export data User --format xlsx --output ./reports/users.xlsx

kaira export data --all --format xlsx     # one workbook, one sheet per model
kaira export data --all --format pdf      # one file per model
```

- Rows stream in batches (`LIMIT`/`OFFSET` on SQL, cursor batching on Mongo) — a table larger than RAM exports fine with or without `--limit`.
- Output defaults to `./exports/<model>_<timestamp>.<ext>`; `exports/` is created and added to `.gitignore` automatically, because an export file *is* customer data sitting in the working tree.
- `--filter` uses the same `key:value` grammar as the rest of Kaira. Equality only — operators are out of scope.

### `kaira export add` — self-serve endpoint (generated API)

```bash
kaira auth add-guard User            # required first — no unguarded exports
kaira export add User --format xlsx
kaira export add Order --format all  # xlsx + pdf + docx
kaira export list
kaira export remove User
```

Generates into the model's **existing** router and service — no new layer:

```
GET /api/v1/users/export?format=xlsx
```

- **Auth-gated by default, no opt-out.** `kaira export add` refuses to run on an unguarded model and points you at `kaira auth add-guard`.
- Rate-limited via `settings.EXPORT_RATE_LIMIT` (default `5/minute`, tighter than a normal GET because one call reads a whole table). The setting is injected into `config/settings.py` on first `export add`, so pre-Phase-7 projects get it too.
- `StreamingResponse`, serialized to a temp file *before* the response starts — a failure returns a real 500 instead of truncating a `200 OK` mid-download.
- Response carries `X-Kaira-Export-Format`, matching the `X-Kaira-DB-Mode` header pattern.
- Raw exception details never reach the client; they go to Loguru and the client gets a generic 500.
- `kaira export remove` deletes the endpoint **and its imports** — marker-delimited blocks, so nothing is left orphaned.

### What is never exported

Any field whose name contains `password`, `hashed_password`, `token`, `secret`, or `api_key` is stripped from every file, in every format, on both paths. There is no flag to keep them, and they are rejected as `--filter` keys too — an equality filter against a hash is a guessing oracle.

`kaira export data --all` against `APP_ENV=production` requires you to type the project name, and `--force` does not buy you past it.

See `kaira guide export` for the full walkthrough.

---

## Monitoring (`kaira monitor`)

Runtime monitoring for a generated project — metrics, Kubernetes-style probes, a
self-hosted mini dashboard, and threshold alerts. No infrastructure, no accounts,
no Prometheus stack to stand up: everything below runs inside the app you already
have.

Entirely opt-in. A project that never runs `kaira monitor init` is byte-for-byte
what it was before.

```bash
kaira monitor init                            # metrics + probes
kaira monitor init --dashboard --auth token   # and the mini dashboard
kaira monitor status                          # configured + live self-check
kaira monitor watch                           # alert when a threshold trips
kaira monitor diff --since yesterday          # compare two snapshots
```

### What `init` adds

| Route | Purpose | Auth |
|---|---|---|
| `GET /metrics` | Prometheus exposition — request counts, latency histogram, errors | none (scrapers have no credentials) |
| `GET /healthz` | Liveness — process is up. Checks nothing external | none |
| `GET /readyz` | Readiness — dependencies reachable, `503` when not | none |
| `GET /_kaira/monitor` | Mini dashboard (opt-in) | **required** |
| `GET /_kaira/monitor/data` | JSON the dashboard polls | **required** |

**`/health` is not touched.** Phase 4 owns it, Docker's `HEALTHCHECK` points at
it, and it behaves exactly as before. The probes are added *beside* it, because
"is the process alive" and "can this instance serve traffic" are different
questions — answering both with one endpoint is how a database blip gets your
healthy process restarted.

The metrics middleware registers **after** the security middleware and reads the
duration that middleware already computed for `X-Response-Time`. One stopwatch
per request, and CORS/security headers keep the position they have always had.

Metric labels use the **route template** (`/api/v1/users/{uuid}`), never the
concrete path. A label per resource id is unbounded cardinality — it takes down
the metrics backend before it tells you anything.

### The mini dashboard

Off by default and not switchable to public:

- `KAIRA_MONITOR_ENABLED=true` is required, or both routes return `404` — the
  same answer an unmounted path gives.
- An auth strategy is required: reuse the project's own guard, or a bearer token
  in `KAIRA_MONITOR_TOKEN` (generated for you, 32+ chars, constant-time compare).

Unlike `/health`, this page reports which routes are hot, which are failing, how
many auth attempts are being rejected, and how close the database is to its plan
limit. That is a map of a system's soft spots.

> **Scope: single worker.** The dashboard's metrics are in-memory and
> per-process. Under one uvicorn worker they are the whole truth; under
> `gunicorn -w 4` you are looking at whichever worker answered the request —
> roughly a quarter of your traffic, not a quarter-scale copy of it. `/metrics`
> has the same property, and that is fine: a scraper hits every replica and
> aggregates. Cross-worker aggregation needs a shared backend and is deliberately
> not built.

### What only Kaira can show you

Because Kaira owns the model → router pipeline and the command history:

- **Model activity** — traffic and errors per *model*, not per URL prefix.
- **Change markers** — `migrate run`, `sync model`, `deploy run` from
  `.kaira/history.jsonl`, drawn on the latency timeline. "Latency jumped right
  after this migration" becomes visible instead of inferred.
- **Self-baseline anomalies** — a route flagged only against its own 7-day p95,
  so a legitimately slow route never trips the flag by being slow. No ML, no
  external service.
- **Security feed** — the 401/403/429 your auth guard and slowapi already
  return, counted. Not a new detection system.
- **Storage runway** — a periodic database-size query and a linear projection:
  *"at current growth, ~19 days to your plan's storage limit."* Set
  `KAIRA_STORAGE_LIMIT_MB` to get a date.

### Structured logs

```bash
KAIRA_LOG_FORMAT=json    # one JSON object per line, on stdout
```

That is how Railway, Render, Fly and CloudWatch ingest logs — they capture the
process's stdout. **Kaira never writes a log file**, and this does not change
that: it is a formatter switch on the sink that was already there.

### Third-party providers

`kaira integrate --provider monitor/sentry|datadog|newrelic` now actually calls
the SDK's `init()` in your lifespan, instead of only installing the package and
writing env keys.

Sampling is cost-conscious because these are metered services: traces at `0.2` in
production and `1.0` in development, via `settings.MONITOR_TRACES_SAMPLE_RATE`
rather than a hardcoded call-site value. Errors are never sampled. A missing
credential logs one line and boots normally — an observability tool must never be
the reason a service fails to start.

Nothing in the three tiers above needs a provider account.

See `kaira guide monitor` for the full walkthrough, or
[`docs/MONITORING_USAGE.md`](docs/MONITORING_USAGE.md) for a command-by-command
reference.

---


## Change Detection

Kaira **never silently overwrites** files. When a file already exists:

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

## Phase 7.5 Presentation & Discovery

### Command Index (`kaira commands`)

Scan or filter all registered commands without executing anything:

```bash
kaira commands                    # View all commands grouped by category
kaira commands --group db         # Show only database commands
kaira commands --search export    # Search across names & descriptions
```

### Brand Banner

Kaira has exactly two banners, and they do different jobs.

| Banner | Job | Where | Frequency |
|---|---|---|---|
| **Large** | First impression — ceremony for the moment a project starts | `kaira init` only | Once per project, ever |
| **Small** | Wayfinding — quiet identity that doubles as a divider | bare `kaira`, `--version`, `about`, `commands` | Many times per day |

The large banner is block art: a five-row lockup composited with a dim shadow
offset one row down and one column right, over the tagline
`Continuous model-level FastAPI scaffolding`. The small banner is a single line
— `⚡ kaira ────… v0.1.0` — whose rule stretches to fill the gap between the
mark and the version, capped at 80 columns.

Every other command gets **no banner**. Neither appears under `--quiet`, and
neither is ever printed twice in one invocation.

Four-tier degradation, resolved once per invocation:

| Tier | Condition | Output |
|---|---|---|
| 1 | `kaira init`, width ≥ 44, colour, UTF-8 | Large banner **with** shadow |
| 2 | `kaira init`, width ≥ 40, UTF-8, no colour (or `NO_COLOR`) | Large banner, **flat** main layer |
| 3 | Width < 40, non-TTY, or a small-banner surface | Small banner |
| 4 | UTF-8 unavailable | `kaira v0.1.0` — plain ASCII |

Piped output never gets block art: `kaira init > log.txt` writes a readable
log, not 200 block characters. Below a width threshold the banner drops a tier
rather than clipping, wrapping, or scaling.

### Welcome Dashboard (bare `kaira`)

Running `kaira` with no arguments inside a project prints the banner and the
project's state — configuration, health, resource counts, and what to do next:

```
  proj29 · api v1
  ────────────────────────────────────────────
    database       postgresql · proj29
    auth           jwt
    ci             github

  ✓ connection     online · connected · localhost:5432
  ✓ auth setup     configured
  ✓ docker         Dockerfile present
  ! migrations     not initialized

  resources
  ────────────────────────────────────────────
    models         5
    routers        5
    tests          0
    last action    generate model User · 2026-08-04

  action required
  ────────────────────────────────────────────
  → kaira migrate init
  → kaira test generate --all
```

Outside a project it prints a short "no project here" body pointing at
`kaira init`. Help is still one keystroke away via `kaira --help`, and the full
index via `kaira commands`.

### Output Language

Every long-running command reads as a sequence of named sections laid out
against one content column, inside one gutter — no full-width boxes, no
per-command divider styles:

```
  scaffold
  ────────────────────────────────────────────
    database       postgresql
    auth           jwt

  ✓ project files  412ms
  ✓ virtualenv     .venv · 2.4s

  database · postgresql
  ────────────────────────────────────────────
  · detected       postgresql localhost:5432
  ! auth required  postgres@localhost:5432 → proj29
                   blank to skip and use offline SQLite
  ? password       ****
  ✓ created        proj29 · user postgres · localhost:5432
  ✓ credentials    .env.development · git-ignored

  ────────────────────────────────────────────
  ✓ proj29 ready in 84.1s
  → cd proj29
  → kaira run
```

The vocabulary lives in `core/ui.py` — `section`, `step`, `note`, `field`,
`subtext`, `hint`, `rule` — and shares its symbols, colours, gutter and rule
width with the progress renderer via `core/theme.py`:

- `✓ ✗ ! ◐ ◌` are **verdicts**; `·` is an **observation** that makes no claim
  either way; a bare label/value **field** is a setting, not a step.
- Labels sit in a fixed column, so values line up down a whole section. The
  symbol column is padded to a uniform width, which keeps the alignment intact
  when symbols fall back to `[ok]` / `[x]` on a non-UTF-8 console.
- Rules are clamped to the content width and to the terminal, whichever is
  narrower — a rule stretched across a 200-column window puts the eye a long
  way from the text it belongs to.

### Multi-Step Progress UI

One shared renderer (`kaira/core/progress.py`) behind `kaira init`, `deps add`,
`deps update`, `generate model`, `generate bulk`, `test generate --all`, and
`seed run --all`. Every phase is visible from the start, so the shape of the job
is clear before it runs:

```
⚡ installing · uv · 12 packages
────────────────────────────────────────────
✓ resolve   12 packages · 340ms
✓ download  18.2 MB · 2.1s
◐ install
  ✓ fastapi 0.115.0
  ✓ sqlalchemy 2.0.36
  ◐ pydantic
  ◌ alembic
  ◌ +7 more
────────────────────────────────────────────
████████████░░░░░░░░░░░░  6/12 · 4.8s
```

- States: `pending ◌` · `active ◐` · `done ✓` · `partial !` · `failed ✗`, each
  with an ASCII fallback (`.`, `>`, `[ok]`, `[!]`, `[x]`).
- The nested list is capped at a fixed height, so the block never grows with the
  project size.
- On full success the detail collapses but the per-phase timings stay — a slow
  resolve means a dependency conflict, a slow download means the network.
- On failure only the failing phase expands, with a short reason and
  copy-pasteable fix commands.
- Under `NO_COLOR`, a pipe, or CI: no animation, no repainting, no cursor codes —
  one plain line per phase as it resolves, then the summary.

### Installer

`uv` is used when it is on `PATH`, otherwise it falls back to `pip` silently.
Either way the full package set goes to a **single** invocation so the resolver
can backtrack across the whole dependency graph. Phase and item states come from
parsing the installer's real output, never from timers. Raw installer output is
never printed: failures are mapped to a short reason (missing PostgreSQL headers,
dependency conflict, network unreachable, …) plus a fix command, so index URLs
and stack traces cannot leak into the terminal.

---

## Documentation Generation (`kaira docs`)

Kaira projects include a deterministic documentation engine that projects internal project state (`.kaira.json`, models, route discovery, and env configuration) directly into markdown reference documents in `./docs`.

```bash
# Generate complete documentation suite
kaira docs generate

# Check documentation freshness against project state (read-only)
kaira docs status

# Surgically regenerate documentation for a single model (preserves other models)
kaira docs generate User

# Generate specific document only
kaira docs generate --only models       # docs/models.md
kaira docs generate --only endpoints    # docs/endpoints.md
kaira docs generate --only erd          # docs/erd.md
kaira docs generate --only config       # docs/configuration.md

# Preview planned changes without writing to disk
kaira docs generate --dry-run

# Specify custom output directory
kaira docs generate --output ./documentation

# Non-interactive CI mode (overwrites silently without prompts)
kaira docs generate --quiet
```

### Generated Documentation Files

| File | Content |
|---|---|
| `docs/README.md` | Navigation index linking all reference docs, project metadata, and pointers to OpenAPI (`kaira api export`) & Postman (`kaira api postman`). |
| `docs/models.md` | Complete model reference with field tables, data types, constraints (e.g. `max_length`, `ge`, `email`), nullability, and relationship links. Supports surgical single-model updates. |
| `docs/endpoints.md` | Discovered API routes grouped by resource tag, HTTP method, authentication requirements (🔒 Required / Public), cache TTL, and rate limits. |
| `docs/erd.md` | Live Mermaid `erDiagram` visualizing entity relationships with exact cardinalities (`||--o{`, `}o--||`, `}o--o{`, `||--||`) for relational databases, or logical document relationships for MongoDB/Atlas/Firestore. |
| `docs/configuration.md` | Environment variable reference detailing key names, ownership, requirements, and placeholder formats. **Zero access to live `.env` files** — secrets are never read or stored. |

---

## Project Structure (Generated)

```
my-api/
├── main.py
├── database.py
├── auth/
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
│   ├── README.md
│   ├── models.md
│   ├── endpoints.md
│   ├── erd.md
│   └── configuration.md
├── alembic/
├── .env
├── .env.example
├── .gitignore
├── Dockerfile
├── requirements.txt
└── .kaira.json
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
pytest tests/ --cov=kaira --cov-report=term-missing
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
