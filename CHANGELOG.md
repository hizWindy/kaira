# Changelog

All notable changes to Kaira (formerly DevFlow) will be documented in this file.

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
