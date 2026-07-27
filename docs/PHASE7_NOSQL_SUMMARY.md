# Phase 7 — NoSQL Provisioning, Seeding & Stats

Status: **Implemented & verified against a live local MongoDB instance.**
Tests: 355 passed, 1 skipped (was 340 — 15 new tests added). Ruff clean on all touched files.

## Problem statement

1. Seeding a MongoDB project inserted nothing, but the CLI reported success — so nothing ever appeared in MongoDB Compass.
2. Seeding needed to work correctly for both relational (SQL) and document (Mongo) projects.
3. After seeding, there was no way to see the resulting table/collection counts.

## Root cause (#1)

`core/database.py` (MongoDB template) declared:

```python
async def init_db(document_models: list) -> None:
```

`document_models` was **required**. The seed script and `seed clear` both called `init_db()` with zero arguments. The resulting `TypeError` was caught by a broad `except Exception`, printed as a harmless notice, and swallowed — so Beanie was never initialized, every `insert()` failed individually, and the script still exited `0` with `"Successfully seeded 0 document(s)"`. The CLI wrapper then printed `✓ Seeded successfully`.

MongoDB also creates databases/collections lazily on first write, so even a working connection produces nothing visible in Compass until data (or an explicit `create_collection`) lands.

## Changes made

### 1. `init_db()` is callable with no arguments
[`kaira/templates/database_mongodb.py.j2`](../kaira/templates/database_mongodb.py.j2)

- `init_db(document_models=None)` — when omitted, calls new `discover_document_models()`, which imports every `Document` subclass under `models/`. This is also required correctness: Beanie can't resolve `Link[...]` fields unless every linked model is registered.
- `resolve_db_name()` replaces `_client.get_default_database()`, which raised `ConfigurationError` for URIs with no `/dbname` path (e.g. `mongodb://localhost:27017`).

### 2. New `kaira db init` — explicit provisioning
[`kaira/commands/db_cmd.py`](../kaira/commands/db_cmd.py)

The document-database counterpart to `kaira migrate run`. Registers all models (building declared indexes), then explicitly creates each collection that doesn't already exist — so the database and its collections become visible in Compass **before** any data is inserted. Relational projects run `Base.metadata.create_all` through the same command, reporting created vs. already-present per table/collection.

### 3. Seeding split by paradigm, not branched inline
[`kaira/core/drivers/base.py`](../kaira/core/drivers/base.py) / [`relational_driver.py`](../kaira/core/drivers/relational_driver.py) / [`document_driver.py`](../kaira/core/drivers/document_driver.py)

New `driver.get_seed_template_name()` — mirrors the existing `get_model_template_name()` / `get_repository_template_name()` pattern.

- [`seed_model_doc.py.j2`](../kaira/templates/seed_model_doc.py.j2) — Beanie (`insert_many`, `Model.count()`)
- [`seed_model_sql.py.j2`](../kaira/templates/seed_model_sql.py.j2) — async SQLAlchemy only (no sync fallback)
- [`_seed_macros.j2`](../kaira/templates/_seed_macros.j2) — single shared macro for sample values, replacing three duplicated field-loops

Also fixed:
- Restored **typed** sample values — `datetime` fields previously seeded the literal string `sample_created_at_1`; now seed real `datetime` objects.
- Removed the sync `SessionLocal` fallback and a double `commit()` bug (`session.begin()` already commits).
- Errors now **propagate** — a failed seed exits non-zero instead of printing `✓`.
- Added `--count N` (default 5) and **idempotency**: skips if the table/collection is non-empty, `--force` to override.
- `seed clear` now **deletes rows/documents but keeps the schema** (table/collection stays visible in Compass), rather than dropping and recreating.

### 4. Post-seed statistics
[`kaira/core/stats.py`](../kaira/core/stats.py) (new)

`collect_db_stats()` / `build_stats_table()` are shared between `kaira db info` and `kaira seed run`, which now prints a before/after table with a signed **Change** column (`+5`, `—`, etc.) after every seed run.

### 5. Fixed a blocking dependency: `DATABASE_URL` resolution
[`kaira/commands/db_cmd.py`](../kaira/commands/db_cmd.py) `_get_database_url()`

`kaira init` writes the connection URL to `.env.<APP_ENV>` (e.g. `.env.development`), but resolution only checked `.env`, so `db info` and the new stats reported "DATABASE_URL not set" on every freshly generated MongoDB project. Precedence now mirrors `config/settings.py`'s own `pydantic-settings` resolution: process env → `.env` → `.env.<APP_ENV>` → literal default in `settings.py`. Commented-out lines are correctly ignored.

## New/changed files

| File | Change |
|---|---|
| `kaira/templates/database_mongodb.py.j2` | `init_db()` optional arg, model auto-discovery, `resolve_db_name()` |
| `kaira/core/drivers/base.py` + `relational_driver.py` + `document_driver.py` | `get_seed_template_name()` |
| `kaira/templates/seed_model_doc.py.j2` | new — Beanie seed template |
| `kaira/templates/seed_model_sql.py.j2` | new — SQLAlchemy seed template |
| `kaira/templates/_seed_macros.j2` | new — shared sample-value macro |
| `kaira/templates/seed_model.py.j2` | removed (superseded by the two above) |
| `kaira/core/stats.py` | new — shared stats collection/rendering |
| `kaira/core/project_runner.py` | new — run code/scripts in the generated project's venv |
| `kaira/commands/seed_cmd.py` | rewired to new templates, `--count`/`--force`, stats, honest failures |
| `kaira/commands/db_cmd.py` | new `db init` command, `db info` refactored onto `stats.py`, `DATABASE_URL` resolution fix |
| `tests/test_phase7_nosql.py` | +15 tests (driver dispatch, typed values, idempotency, stats, URL resolution, `init_db` contract) |
| `CHANGELOG.md` | Phase 7 section added |

## Verified live (MongoDB running on localhost:27017)

- `kaira db init` created `users` and `posts` collections, confirmed visible in Compass with 0 documents
- `kaira db info` correctly listed both collections and counts
- `kaira seed run --all` inserted 5 real documents each, delta table showed `+5`/`+5`
- Re-running skipped with `Change = —`; `--force --count 3` added `+3`
- `seed clear --force` removed documents but both collections remained (`0` docs, not gone)
- Sample field inspected directly via Motor: `joined_at` is a genuine `datetime`, not a string

## Known remaining issue (out of scope for this pass, flagged not fixed)

`kaira add relation` on a MongoDB project still has 3 pre-existing bugs (wrong cardinality string matching, missing `Link` import, invalid `--embedded` syntax). This was verified to now **fail loudly and correctly** — the new seed pipeline surfaces the real `PydanticUserError` and exits 1, instead of silently reporting success as it did before this work. Fixing the relation bugs themselves is the natural next task.
