# Changelog

All notable changes to Kaira (formerly DevFlow) will be documented in this file.

---

## v0.2.6 — Custom Terminal UI & Request Observability Integration

- **Framework Structured Logging Engine**:
  - Brought Phase 8 Loguru logging engine directly into `kaira.app.logging` (`logger`, `detail`, `http`).
  - Added `InterceptHandler` to capture and unify all standard library loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`, `httpx`, `watchfiles`).
  - Demoted Uvicorn boot & reloader noise to `DEBUG` and silenced raw Uvicorn access log lines in favor of Khaira's status-colored output.
- **Request Observability & Unified Error Contract**:
  - Mounted `ObservabilityMiddleware` automatically into `KairaApp` runtime, injecting `X-Request-ID`, `X-Response-Time`, and `X-Kaira-DB-Mode`.
  - Added formatted single-line request logs (`HH:MM:SS INFO GET 200 / · 0.8ms`).
  - Implemented structured error envelopes and handlers for `RequestValidationError` (422), `RateLimitExceeded` (429), `StarletteHTTPException`, and unhandled internal errors (500) with project-only traceback filtering.
- **Server Startup & Reload Cleanliness**:
  - Guarded `reload_includes` in `KairaApp.run()` to only pass when `watchfiles` is actually installed, eliminating the reload warning banner.
  - Startup ready block: prints formatted tree displaying environment, database status, and docs path.

---

## v0.2.5 — Constructor Inversion of Control (IoC), Branded CLI Dashboard & Clean Scaffolding

- **Constructor Inversion of Control (IoC)**:
  - Repository layer injects database session via constructor (`db: AsyncSession = Depends(get_db)`).
  - Service layer injects repository via constructor (`repo: <Model>Repository = Depends()`).
  - Router layer injects service directly (`service: <Model>Service = Depends()`).
  - Completely eliminated `get_db` and session imports from all generated routers.
- **Branded CLI Experience & Logging**:
  - Restored Rich dashboard panel in `khaira run` with database badge, documentation links, hot-reload status, and port shift notes.
  - Formatted Uvicorn logs to match Khaira brand styling with `%H:%M:%S` timestamps and level badges.
- **Template & Scaffolding Cleanup**:
  - Removed redundant `rate_limit.py` from project root while exporting `limiter` from runtime (`khaira.http`).
  - Added `@classmethod` to `parse_allowed_origins` validator in `config/settings.py` template to resolve static typing warnings.
  - Hardened non-interactive init runs against hanging prompts.

---

## v0.2.4 — Full Framework Runtime, Auto-Discovery & Interactive Wizard

Transform Khaira into a unified, crash-free, production-grade FastAPI framework runtime with automated 5-layer pipelines, dynamic discovery, and real database provisioning.

### Features & Fixes

- **Full Framework Runtime (`KairaApp`)**:
  - `kaira init` now defaults to generating `KairaApp`-based architectures across standard and enterprise tiers.
  - Eager auto-registration of all routes in `routers/` and schemas/models in `models/`.
  - Prefix routing normalized to eliminate duplicate sub-path collisions (`/api/v1/users` instead of `/user/users`).
  - Native system endpoints (`GET /` and `GET /health`) reporting engine name and online/offline mode.
  - Native lifecycle hook decorators `@app.on_startup` and `@app.on_shutdown`.
- **Interactive Wizard & Credentials**:
  - `kaira init` prompts for complexity templates (`Standard`, `Enterprise`, `Simple`).
  - Added secure interactive prompt for PostgreSQL/MySQL database passwords (masked), user, host, and port.
  - Added CLI flags `--db-user`, `--db-password`, `--db-host`, and `--db-port`.
  - Database provisioning now creates actual databases on client-server DBMSs with validated credentials.
- **Dependency & Template Integrity**:
  - Added `khaira>=0.2.4` to `requirements.txt.j2` and `pyproject_generated.toml.j2` to resolve startup crash.
  - Modernized `main_simple.py.j2` to use `KairaApp`.
- **CLI De-splicing & Unified Run**:
  - Eliminated regex string-splicing of `main.py` in `wiring.py`, `generate.py`, and `monitor_cmd.py` for `KairaApp` projects with graceful fallback for legacy brownfield projects.
  - Unified `kaira run` to bind `main:app` through `KairaApp` with dynamic port shifting and resolution.
  - Added `kaira/__main__.py` and `khaira/__main__.py` to support `python -m kaira` and `python -m khaira`.

---

## Agent Guidelines & Scaffolded Agent Integration Phase

Support autonomous AI coding assistants (Antigravity, Claude Code, Cursor, Copilot) when developing Kaira or working inside applications scaffolded by Kaira.

### Dual-Agent Architecture

- **Engine Guidelines (`AGENTS.md`)**: Root-level instructions covering Kaira's 5-layer pipeline invariants, additive shortcut safety, non-TTY terminal degradation, and test suite conventions.
- **Scaffolded Project Guidelines (`agents_project.md.j2`)**: Embedded into every `kaira init` project run, giving downstream AI assistants clear rules on layer responsibilities, prohibited cross-layer calls, and Kaira CLI workflows.
- **Automated Init Scaffolding**: `kaira init` automatically renders `AGENTS.md` alongside `README.md`, `.gitignore`, and `pyproject.toml`.
- **Integration Test Suite**: `tests/test_commands.py` verifies `AGENTS.md` presence and tailored contents upon initialization.

---

## Shortcuts & Tab-Completion Phase — Speed for High-Frequency Workflows

Developers run a small handful of commands dozens of times a day: generating models, making migrations, checking status, running tests. Typing `kaira generate model User` or remembering exact argument names adds friction when speed matters.

### Curated Command Shortcuts

A closed table of 12 additive shortcuts for high-frequency commands:

- `g` → `generate model`
- `gb` → `generate bulk`
- `sm` → `sync model`
- `mm` → `migrate make`
- `mr` → `migrate run`
- `st` → `status`
- `up` → `docker up`
- `dn` → `docker down`
- `ds` → `docker status`
- `q` → `quality`
- `t` → `test run`
- `?` → `menu`

Shortcuts are strictly additive: long forms remain canonical everywhere.

**Key design invariants:**
- **Safety guarantee.** Destructive commands (`db reset`, `migrate rollback`, `seed clear`, `docker down --volumes`, etc.) are explicitly blocked and can never have shortcuts.
- **Resolution echo.** Resolving an alias prints a subtle, muted arrow showing the full command being run (`→ kaira generate model User`). The echo is suppressed under `--quiet`, `-q`, or in non-interactive/non-TTY environments, and sensitive arguments (passwords, tokens, keys) are automatically redacted.
- **Normalized history.** Command invocations logged to `.kaira/history.jsonl` and displayed in `kaira recap` always record the normalized long form rather than the alias.
- **Confirmation intact.** Dangerous or multi-step operations that require typed confirmation (e.g. destructive field syncs) still trigger prompts regardless of shortcut invocation.

### Shell Tab-Completion

Full tab-completion across bash, zsh, fish, and PowerShell via `kaira --install-completion`.

- **Dynamic model name completion**: `generate model`, `sync model`, `seed run`, and `test generate` dynamically suggest models defined in `.kaira.json`.
- **Fail-silent & fast**: Completions execute in under 50ms without opening database connections, reading remote resources, or printing error traces on invalid files.
- **Guide completion**: Suggests all registered `kaira guide` topics.

### Discoverability

- `kaira commands` renders a clean, formatted shortcuts table via `data_table()`.
- `kaira guide shortcuts` provides full usage examples, shell quoting notes (such as `kaira '?'` in zsh), and safety details.
- Comprehensive test suite covering safety invariants, shadowing prevention, passthrough fidelity, echo suppression/redaction, history normalization, and completion resilience.

---

## Motion Phase — An Animated Welcome, and Ports That Get Out of the Way

Two things a developer meets constantly: the screen `kaira` prints when they type
it with no arguments, and port 8000 already being taken.

### The welcome surface

Bare `kaira` used to read as a report — a list of settings, then a list of
checks, then a list of commands, all at the same weight. It answered "tell me
everything about this project" when the question is almost always "where is this
project up to".

It now opens as an overview. A headline names the project with a status pill
beside it, a **setup meter** (`setup ████████░░░░ 2/5`) answers how much is done
before anything is read, and the checks beneath it are the detail behind that
fraction. The meter and the *action required* list are derived from one
checklist, so the count and the commands cannot disagree — a dashboard claiming
4/5 above three outstanding items is worse than no dashboard.

Two additions to the vocabulary in `core/ui.py`, available to every command:
`fmt_meter` for completion, and `fmt_pill` for a condition. A pill is a dot, not
a checkmark, because "online" is not something that *succeeded* — the colour says
healthy, the shape says live. Both fit the terminal rather than wrapping: the
meter's bar shrinks to a six-cell floor and the stat row tightens its separator,
because a meter that runs onto a second line has lost the one thing it was for.

### Motion

New `core/motion.py`, with two primitives — `reveal` for a block that cascades
into place, `play` for a line that changes in place. The welcome body cascades;
the `⚡ kaira` mark gets a highlight sweeping once along its rule; `kaira init`'s
block lockup draws in from the top.

Animation in a CLI is a liability unless three properties hold, so all three are
enforced in the motion layer rather than left to call sites:

- **Bounded.** One 340 ms budget for the whole *invocation*, drawn from by
  every effect in turn — not one ceiling per effect, since two effects each
  honouring 340 ms still leaves the developer watching 680 ms. Within an effect
  the per-frame delay is the granted share *divided* by the frame count, so a
  longer surface animates faster rather than taking longer, and a share too
  small to buy a visible step drops the effect instead of overrunning. The wall
  clock of `kaira` never grows with the size of its output.
- **Additive.** A surface composes its lines *before* any of them is printed, and
  hands the list to `reveal`. Piping, redirecting or reading the output back
  gives byte-identical text: the animation adds pauses, never characters. A test
  asserts the animated body equals the still one.
- **Optional.** Not a TTY, `NO_COLOR`, `CI`, `--quiet`, or `KAIRA_NO_MOTION` and
  it degrades to plain printing. Ctrl-C mid-effect flushes the remaining lines
  immediately instead of leaving half a surface on screen.

The mark animates on bare `kaira` and nowhere else. `--version` and `about` are
read by scripts and by people in a hurry, and neither wants the mark to take a
beat before the answer.

### Ports

Port 8000 is the FastAPI default, which makes it the *shared* default — running a
second Kaira project, or one beside any other uvicorn app, meets a taken port as
routine rather than as a fault. `kaira run` now treats it that way: it finds the
next free port, binds there, and says so in the launch banner.

```
Port   8001  moved from 8000 — another server is on it
URL    http://127.0.0.1:8001
```

The probe in `core/ports.py` **binds rather than connects**. "Is something
listening there" and "can I listen there" are different questions, and only the
second decides whether the server starts — a socket bound without `listen`, or
bound on another interface, answers the first one wrong. `SO_REUSEADDR` is set on
POSIX, where it stops a lingering `TIME_WAIT` socket reporting a free port as
taken, and *not* on Windows, where it does the opposite and would let the bind
succeed on top of a live server. An unrecognised refusal counts as free: shifting
to 8001 would not fix an unresolvable host, so the server gets to report the real
error itself.

The scan is bounded to 20 consecutive ports. Twenty taken in a row is a machine
problem that a twenty-first will not fix, and an unbounded walk to 65535 would
hang the launch instead of reporting it.

`--strict-port` opts out, for callers where the number is part of a contract — a
registered OAuth callback, a reverse proxy, a published container port. It fails
with a clear panel rather than a traceback.

Because the port is no longer a constant, the launcher records the bound address
in `.kaira/runtime.json` for the lifetime of the run, and `kaira api`, `status`,
`profile`, `loadtest` and `monitor` resolve their base URL from it instead of
assuming 8000. The record is confirmed against the port before it is trusted: a
crashed server leaves its file behind, and pointing `kaira api` at a port nobody
holds is worse than pointing it at the default, because the wrong address then
looks deliberate. The welcome dashboard reads the same record, so it reports a
server on 8001 as running rather than claiming nothing is up.

---

## Monitoring Phase — Metrics, Probes, Dashboard & Alerts

Kaira could scaffold a production backend and then tell you nothing about it once
it was running. This phase adds runtime monitoring, in three tiers, and adds it
strictly on top of what already existed — `/health`, the security middleware, and
the `integrate monitor` stub are all still exactly where they were.

### Tier 1 — Essentials

`kaira monitor init` scaffolds `core/metrics.py` (Prometheus counters and a
latency histogram), `middleware/metrics.py`, and `routers/probes_router.py`,
then wires them into `main.py` **through the standard diff/confirm prompt**.

Three new routes, all unauthenticated for the same reason `/health` is — a
scraper and a kubelet have no credentials — and all rate-limited at `300/minute`:

```
GET /metrics    Prometheus exposition: counts, latency, errors
GET /healthz    liveness  — process is up, checks nothing external
GET /readyz     readiness — dependencies reachable, 503 when not
```

`/health` is untouched. The probes are added beside it, because a single endpoint
wired to both probe types is how a 30-second database blip gets a healthy process
restarted. Docker's `HEALTHCHECK` still points at `/health`, and a regression test
asserts the `health_check` function is byte-identical before and after.

The metrics middleware registers **after** `register_security_middleware(app)` —
which, because Starlette applies user middleware outermost-last, wraps it rather
than displacing it. That ordering is also what lets it read the duration the
security middleware already computed for `X-Response-Time`: one stopwatch per
request, not two.

Labels carry the route template (`/api/v1/users/{uuid}`), never the concrete
path. A label per resource id is unbounded cardinality — it exhausts the metrics
backend before it tells you anything. Unmatched requests collapse to a single
`unmatched` label, so URL spraying cannot inflate the label set either.

### Tier 2 — Mini dashboard

`kaira monitor init --dashboard` adds a self-hosted page at `/_kaira/monitor`,
backed by an in-memory rolling window and polling `/_kaira/monitor/data`. Uptime,
error rate, p50/p95/p99, a latency sparkline with volume bars, top routes by
traffic and by latency, dependency health.

Self-contained: no CDN, no font host, no analytics. Styled from Kaira's own
design tokens, and it respects `prefers-color-scheme` and
`prefers-reduced-motion`.

It ships **off** and cannot be turned on halfway. `KAIRA_MONITOR_ENABLED=true` is
required or both routes return 404 — the same answer an unmounted path gives — and
an auth strategy must be chosen at scaffold time: reuse the project's own guard,
or a generated bearer token in `KAIRA_MONITOR_TOKEN` with a constant-time compare
and a 24-character floor. There is no public option; unlike `/health`, this page
is a map of a system's soft spots.

**Scope, stated rather than implied:** the window is per-process. Under one
uvicorn worker it is the whole truth; under `gunicorn -w 4` it is one worker's
view. The page says so on its own face, the payload carries it in `scope`, and
`kaira monitor status` repeats it. Cross-worker aggregation needs a shared
backend and is not built here.

### Tier 3 — What only Kaira can see

Possible because Kaira owns the model → router pipeline and the command history:

- **Model activity** — traffic and errors per *model*, not per URL prefix. Each
  generated router now declares `KAIRA_MODEL`; existing projects fall back to the
  router tag, so nothing needs regenerating.
- **Change markers** — `migrate run`, `sync model`, `deploy run` read from
  `.kaira/history.jsonl` and drawn on the latency timeline. Read-only; this phase
  adds no logging surface.
- **Self-baseline anomalies** — a route compared only against its own p95 over a
  rolling 7 days. No ML, no external service, and a legitimately slow route never
  trips the flag by being slow.
- **Security event feed** — the 401/403/429 the auth guard and slowapi already
  return, counted. A feed, not a detector.
- **Storage runway** — a periodic (≥15 min) database-size query and a linear
  projection: *"at current growth, ~19 days to your plan's limit."* Declares
  nothing until it has two samples to draw through.

### New commands

```
kaira monitor init [--dashboard] [--auth reuse|token] [--force] [--quiet]
kaira monitor status [--url ...]
kaira monitor watch [--interval] [--error-rate] [--p95] [--once]
kaira monitor diff [--since yesterday|week|hour|<ISO timestamp>]
```

`watch` alerts by desktop notification — no alerting service, no account —
firing on the *transition* into a breach rather than on every poll. An optional
`KAIRA_MONITOR_WEBHOOK_URL` also posts to Discord or Slack; that URL is a
credential, so it is only ever printed masked. It reads the dashboard endpoint
when available and falls back to parsing `/metrics`, so it works on a Tier 1
project with no dashboard.

`diff` compares snapshots written by `status` and `watch`, in the same `+`/`-`
language as `sync model --dry-run`, with direction that knows more requests is
good and more errors is not.

### JSON log mode

`KAIRA_LOG_FORMAT=json` switches `core/logger.py`'s existing sink to one JSON
object per line, **on stdout**. That is how Railway, Render, Fly and CloudWatch
ingest logs. Default output is unchanged.

Still no log files — a file inside a container is invisible to the platform
collecting stdout, grows until the disk fills, and needs rotation config to
survive. Structured mode also never enables Loguru's `diagnose`, which would ship
local variable values to a third-party aggregator.

### Real SDK initialisation

`kaira integrate --provider monitor/sentry|datadog|newrelic` installed the SDK
and wrote env keys but never called `init()`. It now generates
`core/monitor_sdk.py` and starts it from the lifespan, through the same
diff/confirm prompt.

Sampling is cost-conscious because these are metered services: traces at `0.2` in
production, `1.0` in development, via `settings.MONITOR_TRACES_SAMPLE_RATE`
rather than a hardcoded call-site value. Errors are never sampled. Sentry is
initialised with `send_default_pii=False`. A missing credential logs one line and
boots normally — observability must never be the reason a service fails to start.

Entirely opt-in: nothing in Tiers 1–3 needs a provider account.

### Also

- `kaira guide monitor`, a `docs/MONITORING_USAGE.md` command reference, and a
  README section.
- Docker recognises monitoring through the existing dynamic rendering — one
  registry-driven header line, no compose service, no special-casing. There is
  no Prometheus/Grafana/Loki stack in this phase, by design.
- New `.kaira.json` flags: `monitor_metrics`, `monitor_probes`,
  `monitor_dashboard`, `monitor_dashboard_auth`, `monitor_json_logs`.
- 133 new tests, including regressions pinning `/health` and middleware order.

---

## Phase 8 — Runtime Display & Error Handling

The generated app printed five to six lines for a single `GET`, in three
competing styles, and reported a crash as one `repr()` on a red line. This pass
rebuilds what a developer sees while `kaira run` is attached.

### 1. One line per request

`core/logger.py` now formats through a callable Loguru formatter, which lets a
request line carry its own colour without embedding markup in the message — a
URL path containing `<` can neither break the layout nor inject terminal
styling.

```
12:58:05  INFO      GET    200  /api/v1/users/list  ·  1.4ms
12:58:06  WARNING   GET    404  /api/v1/users/abc123  ·  0.8ms  · req 6af07350
```

Colour is signal, not decoration: the timestamp and structural glyphs are dim,
the level word carries severity, and within a request line only the status code
and a slow duration (≥500 ms amber, ≥1500 ms red) are tinted. The correlation id
appears only when the request failed, or under `--debug`.

Removed from the default stream: uvicorn's access log (a second, poorer copy of
the same line), its boot chatter, `watchfiles` change notices, `httpx`'s
per-outbound-call line, and uvicorn's duplicate traceback for an exception the
app already reported. All demoted to DEBUG, not dropped.

Router entry traces and service read traces are now DEBUG; state changes
(`created`/`updated`/`deleted`) stay at SUCCESS.

### 2. Multi-part events read as one block

`detail()` renders aligned continuation lines under the message column, so a
startup, a rejection or a crash is one visual unit:

```
12:58:01  SUCCESS   proj15 ready
                    ├─ environment  development
                    ├─ database     mongodb · proj15 · online
                    ├─ models       BlacklistedToken, User
                    └─ docs         /docs
```

### 3. Restructured error reporting

* A crash prints one block — request id, client, reason — followed by a
  traceback filtered to **application frames only**. The starlette/anyio/uvicorn
  plumbing that made the old traceback unreadable is gone, as is the middleware's
  own `call_next` frame.
* Ordering is consistent for every failure mode: the diagnostic block first, then
  the status-coloured request line that summarises it.
* Validation failures list each offending field instead of dumping pydantic's
  raw error list.
* An unhandled exception used to produce **no** completion line at all, because
  the generic handler runs outside the logging middleware. It now does.

### 4. One error contract

Validation, HTTP, rate-limit and crash responses all return the same envelope,
adding a structured `error` object beside the original `detail` key (kept, so
existing clients and generated tests are unaffected):

```json
{
  "detail": "...",
  "error": {
    "code": "internal_error", "status": 500,
    "method": "GET", "path": "/api/v1/boom",
    "request_id": "ad6b5a2a"
  }
}
```

`request_id` matches the `X-Request-ID` response header and the id in the
terminal, so a reported failure is findable without guessing. Every response also
carries `X-Response-Time`. Internal exception text is included only outside
production.

### 5. `kaira run` flags and honest exits

* `--debug` — per-layer traces, request ids on every line, full tracebacks with
  local values, and uvicorn's real lifecycle. `--access-log` restores uvicorn's
  own access line.
* A non-zero server exit printed the same neutral "Server stopped." panel as a
  clean `Ctrl+C`. It now reports the exit code, names the likely causes (port in
  use, import error, missing package, unreachable database), and propagates the
  code.

Environment overrides in the generated app: `KAIRA_LOG_LEVEL`,
`KAIRA_ACCESS_LOG`, `KAIRA_DIAGNOSE`, `KAIRA_LOG_SKIP_PATHS`, plus standard
`NO_COLOR` / `FORCE_COLOR`.

---

## Phase 7 — NoSQL Provisioning, Seeding & Stats

### 1. `init_db()` is callable without arguments

`core/database.py` (MongoDB) declared `init_db(document_models: list)` as a required
parameter, but seed scripts and `seed clear` called `init_db()` with none. The
resulting `TypeError` was swallowed by a broad `except`, so Beanie was never
initialised, every insert failed, and the CLI still reported success.

* `init_db(document_models=None)` now falls back to `discover_document_models()`,
  which imports every Beanie `Document` under `models/`. Registering the full set
  is also required for `Link` fields to resolve.
* `resolve_db_name()` replaces `get_default_database()`, which raised
  `ConfigurationError` for URIs without a path (e.g. `mongodb://localhost:27017`).

### 2. `kaira db init` — explicit provisioning

MongoDB creates databases and collections lazily, so a successful connection
alone leaves nothing visible in MongoDB Compass. `kaira db init` is the document
counterpart to `kaira migrate run`: it registers models, builds declared indexes,
and explicitly creates each collection, reporting what was created versus already
present. Relational projects run `create_all` through the same command.

### 3. Seeding reworked for both paradigms

* Seed templates are dispatched via `driver.get_seed_template_name()` —
  `seed_model_doc.py.j2` (Beanie) and `seed_model_sql.py.j2` (async SQLAlchemy) —
  replacing a single template that branched inline and duplicated its field-value
  logic three times. Sample values now live in one shared macro.
* Restored typed sample values: `datetime` fields previously seeded the *string*
  `sample_created_at_1`.
* Removed the sync `SessionLocal` fallback and the double `commit()`; errors now
  propagate so a failed seed exits non-zero instead of printing `✓`.
* Added `--count N`, and idempotency — a non-empty table or collection is skipped
  unless `--force` is passed.
* `seed clear` deletes documents/rows while keeping collections and tables, so the
  schema stays visible in Compass.

### 4. Post-seed statistics

`kaira seed run` prints per-table/collection counts with a signed Change column
comparing before and after. The collection logic lives in `kaira/core/stats.py`
and is shared with `kaira db info` rather than duplicated.

### 5. `DATABASE_URL` resolution honours the `APP_ENV` profile

`kaira init` writes the URL to `.env.<APP_ENV>`, but resolution only read `.env`,
so `db info` reported "DATABASE_URL not set" for a freshly generated MongoDB
project. Precedence now mirrors `config/settings.py`: process environment, `.env`,
`.env.<APP_ENV>`, then the literal default in `settings.py`. Commented-out lines
are correctly ignored.

---

## Recent Database & Migration Enhancements

This section details the latest enhancements made to the CLI to support real database connections, zero-configuration migrations, dynamic SQLite fallbacks, and live schema inspection.

### 1. Real Database Connection Diagnostics (`kaira db connect` / `status`)

* **Live Credential Checks:** 
  * **SQL Databases (PostgreSQL, MySQL):** Initiates an async engine connection using SQLAlchemy and runs a test query (`SELECT 1`).
  * **NoSQL Databases (MongoDB):** Establishes a connection using Motor and triggers an admin `ping` command.
  * **SQLite:** Validates local file access and write permissions.
* If credentials are invalid or the target database does not exist, the CLI cleanly reports the exact database driver error.

---

### 2. Table & Collection Inspector (`kaira db info`)

* Introduced `kaira db info` to display database schema details directly in the console using a Rich Table showing all active tables/columns or collections/documents.

---

### 3. Dynamic Local SQLite Fallback (`config/settings.py` resolution)

* Patched environment loader to detect when `DATABASE_URL` is omitted or commented out in `.env`.
* Dynamically parses `config/settings.py` to extract local fallback configuration (e.g. `sqlite+aiosqlite:///./project.db`).

---

### 4. Zero-Configuration Migrations (`kaira migrate`)

* Automated migration initialization: Running `kaira migrate make`, `kaira migrate run`, or `kaira migrate rollback` checks for `alembic.ini` and `alembic/env.py` and auto-initializes Alembic if missing.
* Auto-configures `env.py` to discover and register all model metadata automatically.

---

### 5. File Reload Protection & Windows Encoding Guard

* **Reload loop fix:** Uvicorn watch options ignore `*.db`, `*.db-journal`, `*.db-wal`, and `.log` files to prevent infinite reload loops upon local database writes.
* **Unicode terminal fix:** Environment encoding explicitly set (`PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1`) to prevent Windows console `UnicodeEncodeError`.
