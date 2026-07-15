# DevFlow — Phase 5 Build Instructions

> **For use with Antigravity.** This file gives the agent full context on the DevFlow CLI and the Phase 5 scope. Phases 1–4 are complete and must not be modified — only the work described below should be implemented.
>
> **Before beginning any work, confirm you have read and understood this entire prompt.**

---

## 0. Agent Operating Rules

- Treat this document as the source of truth for Phase 5 scope. Do not invent commands, flags, or file paths not listed here.
- **Do not rebuild, refactor, or regress any existing Phase 1, 2, 3, or 4 command.** If a change to earlier-phase code appears necessary, stop and flag it instead of proceeding.
- Follow the existing architecture, naming conventions, and code style found in `devflow/commands/`, `devflow/core/`, and `devflow/templates/`.
- Work through the **Build Order** in Section 6 sequentially.
- After each feature group is implemented, run `ruff check --fix`, `ruff format`, `mypy`, and `bandit -ll` before moving to the next group.
- Do not mark a Deliverables Checklist item done until its tests pass at ≥80% coverage.

---

## 1. Project Summary (context)

**DevFlow** is an automated scaffolding CLI for FastAPI backend development. It works at the **model level** — every `devflow generate model` produces all 5 architectural layers (Model → Repository → Schema → Service → Router) with security enforced by default.

| Part | Technology |
|---|---|
| Language | Python 3.10+ |
| CLI Framework | Typer + Rich |
| Interactive prompts | InquirerPy |
| Template engine | Jinja2 |
| Logging | Loguru (terminal only — never log files) |
| Formatter/Linter | Ruff |
| Target stack | FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic (or Beanie + Motor for MongoDB) |
| Project memory | `.devflow.json` at project root |

### Already built (Phases 1–4, ~172 commands — DO NOT MODIFY)

| Phase | Covers |
|---|---|
| 1 | Core 5-layer scaffolding, relationships, migrations, config utilities |
| 2 | Auth (JWT/OAuth2/API key), security tests, env validation, Docker, seeding, versioning, WebSocket, CI/CD, audit/health |
| 3 | Named init + wizard, multi-DB (PostgreSQL/MySQL/MongoDB/SQLite), Rich installer, `guide`, Loguru, `/api/v1` prefixed routes, clean code |
| 4 | Welcome dashboard, smart errors, next-steps, progress bars, colored diff, typed confirmations, fuzzy typos, `status`, `recap`, `db`, `deps`, `cache`, `task`, `integrate`, `api`, `quality`, `profile`/`loadtest`, `deploy`, `middleware`, `event`, `notify`, `flags`, `health-endpoint`, `run` |

**Implicit security applied on every generation (must remain intact):** slowapi rate limiting, ORM-only queries, Pydantic field limits, restrictive CORS, security headers, bcrypt (cost 12), no raw exceptions to clients, try/finally on DB sessions, UUID external / int PK internal, no secrets in logs.

---

## 2. Phase 5 Scope Overview

Phase 5 has two goals:

1. **UI/UX Modernization** — bring every interactive surface of the CLI up to a consistent, modern, polished standard: spinners, animated loaders, unified arrow-key selection, consistent theming, better tables, keyboard shortcuts, first-run onboarding.
2. **Cloud Databases + Offline Fallback** — first-class support for **Supabase**, **MongoDB Atlas**, and **Firebase (Firestore)** as cloud database options, with an automatic **cloud → local fallback** mode so the generated app keeps running when the cloud connection drops.

---

## 3. Feature Specifications — PART 1: UI/UX Modernization

### UX 10 — Unified Design System (`core/theme.py`)

Create a single theme module that every command imports. No command may define its own colors or symbols inline anymore.

```python
# core/theme.py
"""DevFlow terminal design system — single source of truth for all UI."""

class Theme:
    PRIMARY = "bold cyan"
    SUCCESS = "bold green"
    WARNING = "bold yellow"
    ERROR = "bold red"
    MUTED = "grey58"
    ACCENT = "magenta"

class Symbols:
    OK = "✅"
    FAIL = "❌"
    WARN = "⚠️"
    PENDING = "⏳"
    SKIP = "⏭️"
    BOLT = "⚡"
    ARROW = "→"
    POINTER = "❯"
```

Rules:
- Refactor is **additive**: new Phase 5 code uses the theme; existing Phase 1–4 output strings are left untouched (no regression risk). Migrating old commands to the theme is out of scope.
- Respect `NO_COLOR` env var and non-TTY output (CI logs): degrade to plain ASCII symbols (`[ok]`, `[x]`, `[!]`) automatically. Add `core/theme.py::is_interactive()` helper used everywhere.

### UX 11 — Modern Loading States

Replace every bare "waiting" moment with a Rich spinner or animated status line. No command may ever appear frozen.

```
⠋ Connecting to Supabase...           (spinner, dots style)
⠙ Resolving dependencies...
✅ Connected in 214ms
```

Rules:
- Use `rich.status.Status` / `console.status()` for indeterminate waits, `rich.progress.Progress` (already in Phase 4) for determinate ones.
- Spinner style: `dots` everywhere — one style, consistent.
- Every spinner line must resolve to a final ✅/❌/⚠️ line with elapsed time (`in 214ms` / `in 1.2s`). Never leave a spinner's last frame on screen.
- Anything that can exceed 500ms gets a spinner: DB connections, pip installs, HTTP calls, file scans, template rendering of bulk jobs.
- In non-interactive mode (CI / piped output): print `... connecting to Supabase` then the result line — no animation codes.

### UX 12 — Unified Arrow-Key Selection Everywhere

Every choice DevFlow presents must be an InquirerPy arrow-key prompt — never "type 1, 2 or 3", never bare `input()`.

```
? Select your database:
  ❯ PostgreSQL        Relational · Alembic migrations
    MySQL             Relational · Alembic migrations
    MongoDB           Document · Beanie ODM
    SQLite            Relational · zero-config local
    ─────────────────
    Supabase          ☁️ Cloud · PostgreSQL-compatible
    MongoDB Atlas     ☁️ Cloud · MongoDB-compatible
    Firebase          ☁️ Cloud · Firestore document store
```

Rules:
- Build a shared wrapper `core/prompts.py` with: `select()`, `multi_select()`, `confirm()`, `text()`, `secret()` — all styled from `core/theme.py`. All new prompts go through this wrapper only.
- Every choice shows a right-aligned muted description (second column), as above.
- `secret()` masks input (for connection strings / API keys) and never echoes the value back.
- Long lists (>8 items) get fuzzy-search filtering (InquirerPy fuzzy prompt).
- Every prompt supports `Ctrl+C` → clean exit with `"Cancelled."` — never a traceback.
- Every interactive prompt must have a non-interactive escape hatch: the equivalent CLI flag. If stdin is not a TTY and a required value is missing, error with the exact flag to pass (Phase 4 smart-error format).

### UX 13 — Consistent Panel & Table Language

Standardize every output block:

- **Panels**: rounded borders, title on the left as `⚡ DevFlow — <Title>`, subtitle on the right showing elapsed time or date where relevant.
- **Tables**: `rich.table.Table` with `box.SIMPLE_HEAD`, header in `Theme.PRIMARY`, numeric columns right-aligned, status columns using `Symbols`.
- **Key-value blocks** (like `db status`): two-column grid, keys muted, values normal.

Add `core/ui.py` with helpers: `panel()`, `kv_table()`, `data_table()`, `success_footer()`, `error_footer()` — new Phase 5 commands must use these instead of hand-rolling Rich layouts.

### UX 14 — First-Run Onboarding

The very first time `devflow` is executed on a machine (no `~/.devflow/config.json`), show a one-time interactive onboarding:

```
⚡ Welcome to DevFlow!

? What describes you best?
  ❯ New to FastAPI       → suggests devflow guide + tutorial tips
    Experienced dev      → minimal hints, straight to work

? Enable anonymous usage stats to improve DevFlow? (no code, no secrets, ever)
  ❯ No
    Yes
```

Rules:
- Writes `~/.devflow/config.json` (`experience_level`, `telemetry`, `theme`).
- **Telemetry defaults to No / opt-in only.** If enabled, it may only ever record command *names* and durations — never arguments, paths, or project names. If not implemented as a real backend yet, store the preference but send nothing.
- Onboarding is skippable with any flag/args present, and never shown in CI (non-TTY).
- `devflow config reset-onboarding` re-triggers it.

### UX 15 — Command Palette (`devflow menu`)

An interactive, fuzzy-searchable menu of all ~175 commands for discoverability:

```
devflow menu

? Search commands: mig▌
  ❯ migrate make          Create a new migration
    migrate run           Apply pending migrations
    migrate rollback      Revert last migration
    migrate init          Initialize Alembic
```

Selecting a command that needs arguments launches the relevant prompts (via `core/prompts.py`), then shows the equivalent raw command before running it, so users learn the CLI as they go:

```
Running: devflow generate model User --fields "name:str, email:str"
```

### UX 16 — Refined `--help` Output

Style Typer's help output using `rich_markup_mode="rich"`: group commands by category (Scaffolding, Database, Security, Quality, Deploy, Cloud...), one-line descriptions, examples section at the bottom of each group's help.

### UX 17 — Result Summaries with Timing

Every command that does work ends with a one-line footer:

```
────────────────────────────────────────────────
✅ Done in 1.4s · 5 files generated · 0 warnings
```

Implement once in a decorator (`@with_summary`) applied to new Phase 5 commands; do not retrofit old commands.

---

## 4. Feature Specifications — PART 2: Cloud Databases (`devflow cloud`)

### FEATURE 16 — Cloud Database Providers

Extend the database options with three cloud providers:

| Provider | Protocol | Maps to existing engine | Fallback pair |
|---|---|---|---|
| **Supabase** | PostgreSQL wire protocol | SQLAlchemy async (asyncpg) — same templates as PostgreSQL | SQLite (local) |
| **MongoDB Atlas** | MongoDB (`mongodb+srv://`) | Beanie + Motor — same templates as MongoDB | Local MongoDB, else JSON snapshot read-cache |
| **Firebase (Firestore)** | Firestore SDK | **New template set** `templates/firestore/` | Local JSON snapshot read-cache |

Commands:

```
devflow cloud connect                 # interactive provider wizard
devflow cloud connect --provider supabase|atlas|firebase
devflow cloud status                  # provider, region, latency, fallback state
devflow cloud test                    # round-trip health check
devflow cloud disconnect              # revert to a local database (typed confirm)
devflow cloud fallback status         # show current mode + queued writes
devflow cloud fallback sync           # manually push queued writes to cloud
```

#### `devflow cloud connect` wizard flow

1. Arrow-key provider selection (UX 12 style, with descriptions).
2. Provider-specific guided input using `secret()` prompts:
   - **Supabase**: project URL + database password → assembles the asyncpg connection string. Ask **Pooled (pgbouncer, port 6543)** vs **Direct (port 5432)** with a short explanation of each; recommend *Direct* for Alembic migrations and *Pooled* for the app at runtime — store both if provided.
   - **Atlas**: paste `mongodb+srv://` string (validated by regex before accepting).
   - **Firebase**: path to the service-account JSON file → validated to exist and parse; path stored in settings, file itself **never** copied into the repo. The wizard must add the filename pattern to `.gitignore`.
3. Live connection test with spinner (UX 11). On failure: Phase 4 smart-error format with provider-specific hints (IP allowlist for Atlas, paused project for Supabase free tier, wrong service-account project for Firebase).
4. On success: update `.devflow.json` (`"database": "supabase"`, `"cloud": true`, `"fallback": {...}`), write env keys to all `.env` files, register required settings fields.

#### Supabase / Atlas specifics

- Supabase reuses **relational templates unchanged** — it is PostgreSQL. Only the connection layer and env keys differ. Alembic migrations fully supported (run against the *direct* connection).
- Atlas reuses **MongoDB templates unchanged**. No migrations (schemaless), same as local MongoDB.
- `devflow db switch` (Phase 4) must recognize the three new provider names and route to `cloud connect`.

#### Firebase specifics

- New `templates/firestore/` set: document model, repository (Firestore async client), schema (Pydantic v2), service, router — same 5-layer shape, strict layer separation preserved.
- No Alembic; block `devflow migrate *` on Firestore projects with the Phase 4 smart-error format (mirror the existing MongoDB behavior).
- All Firestore access via the official `google-cloud-firestore` async client — installed via the Phase 3 Rich installer.
- Document IDs: expose UUIDs externally exactly like the other engines.

### FEATURE 17 — Cloud → Local Fallback

Generate a resilience layer so the user's app survives cloud outages.

`devflow cloud connect` (or `devflow cloud fallback enable`) generates `core/fallback.py` into the user's project:

```
Modes:
  CLOUD      normal operation, all reads/writes hit the cloud
  DEGRADED   cloud unreachable → reads served locally, writes queued
  RECOVERED  cloud back → queued writes replayed, then return to CLOUD
```

Behavior spec:

- **Health probe**: a lightweight ping to the cloud DB every N seconds (default 30, configurable via `FALLBACK_PROBE_INTERVAL`). 3 consecutive failures → enter DEGRADED. First success after DEGRADED → enter RECOVERED → replay queue → CLOUD.
- **Reads in DEGRADED**:
  - Supabase → read from a local SQLite mirror at `.devflow/fallback.db` (same models — SQLAlchemy makes this nearly free).
  - Atlas → local MongoDB if reachable, else the JSON snapshot cache at `.devflow/fallback/`.
  - Firebase → JSON snapshot cache at `.devflow/fallback/`.
  - Mirror/snapshot freshness: refreshed opportunistically after successful cloud reads (write-through cache), so DEGRADED serves the last-known-good data. Responses in DEGRADED include header `X-DevFlow-Mode: degraded` so clients can react.
- **Writes in DEGRADED**: appended to a durable local queue `.devflow/fallback/write_queue.jsonl` and acknowledged to the client with `202 Accepted` + `X-DevFlow-Mode: degraded` (NOT a fake `200/201` — never lie about persistence).
- **Replay on recovery**: queue replayed in order, idempotently (each queued write carries a UUID; replays are skipped if the UUID already applied). Conflicts (row changed in cloud since queueing) are **not silently overwritten** — conflicting entries are moved to `.devflow/fallback/conflicts.jsonl` and surfaced by `devflow cloud fallback status`.
- **Never lose the queue**: append-only file, fsync after each write, gitignored.
- **Security**: the local mirror and queue may contain user data → files created with `0600` permissions, directory gitignored, and `devflow cloud fallback status` never prints row contents (counts only). Queued writes never include raw passwords — hashing happens *before* queueing (service layer order preserved).
- **Opt-out**: `devflow cloud fallback disable` removes the wiring; the wizard asks whether to enable fallback (default: Yes).
- **Off in tests**: generated test suite forces CLOUD mode with a mocked client — fallback logic gets its own dedicated generated tests instead.

```
devflow cloud fallback status

⚡ DevFlow — Fallback Status
────────────────────────────────────────────────
  Provider:       Supabase
  Mode:           ⚠️ DEGRADED (since 14:02, 6m ago)
  Local mirror:   ✅ fresh (last sync 14:01)
  Queued writes:  17 pending
  Conflicts:      0
  Next probe:     in 12s
────────────────────────────────────────────────
  → devflow cloud fallback sync   (manual replay attempt)
```

### FEATURE 18 — Env & Validation Integration

- New settings keys per provider (all via `settings`, never hardcoded):
  - Supabase: `SUPABASE_DB_URL`, `SUPABASE_DB_URL_DIRECT`
  - Atlas: `ATLAS_URI`
  - Firebase: `FIREBASE_CREDENTIALS_PATH`, `FIREBASE_PROJECT_ID`
  - Fallback: `FALLBACK_ENABLED`, `FALLBACK_PROBE_INTERVAL`
- `devflow env validate` (Phase 2) must additionally check: SSL enforced on cloud URLs, Firebase credentials file exists and is **not** tracked by git, no cloud credentials present in `.env.example` (placeholders only).
- All printed cloud connection strings masked (`user:****@host`) — same Phase 4 rule.
- `devflow deploy checklist` (Phase 4) gains: "Fallback queue empty" and "Cloud credentials referenced from secret store" checks.

---

## 5. New Guide Pages

```
devflow guide cloud
devflow guide fallback
devflow guide menu
```

Each with real copy-pasteable examples in the existing guide style.

---

## 6. Recommended Build Order

1. `core/theme.py` + `core/ui.py` + `core/prompts.py` (foundation for everything)
2. UX 11 loading states + UX 13 panels/tables (used by all later features)
3. UX 17 `@with_summary` decorator
4. UX 12 selection wrapper rollout in new code paths
5. UX 14 first-run onboarding
6. UX 16 refined `--help`
7. UX 15 `devflow menu` (needs the prompt wrapper + full command registry)
8. FEATURE 16 — Supabase (smallest delta: reuses relational templates)
9. FEATURE 16 — Atlas (reuses MongoDB templates)
10. FEATURE 16 — Firebase (new `templates/firestore/` set)
11. FEATURE 17 — fallback engine (probe → modes → queue → replay), per provider in the same order
12. FEATURE 18 — env validation + deploy checklist integration
13. 3 new `guide` pages, README, tests

---

## 7. Global Rules (Non-Negotiable)

**Security (carried forward + new):**
- No raw SQL — ORM/ODM/SDK only.
- No secrets in logs, terminal output, history, or URLs; mask every printed connection string.
- Firebase service-account JSON never committed, never copied into the repo, always gitignored.
- Fallback queue/mirror files: `0600` perms, gitignored, contents never printed.
- Queued writes acknowledged as `202`, never faked as completed.
- Destructive commands (`cloud disconnect`, queue purge) require typed confirmation; blocked/`--force`-immune in production per Phase 4 rules.
- Telemetry strictly opt-in; command names + durations only.

**Clean code (carried forward):**
- Module + function docstrings, full type hints, no hardcoded values, strict layer separation, `ruff check --fix` + `ruff format` after every generation.

**UI consistency (new):**
- All new interactive input goes through `core/prompts.py`; all new output through `core/ui.py` + `core/theme.py`.
- Every wait >500ms has a spinner; every spinner resolves to a result line.
- Everything degrades gracefully to plain text when non-TTY or `NO_COLOR`.
- No Phase 1–4 command output is modified.

---

## 8. Deliverables Checklist

- [ ] `core/theme.py` design system + `NO_COLOR`/non-TTY degradation
- [ ] `core/ui.py` panel/table helpers
- [ ] `core/prompts.py` unified arrow-key prompt wrapper (select, multi, confirm, text, secret, fuzzy)
- [ ] Modern spinners on every >500ms wait, all resolving to timed result lines
- [ ] `@with_summary` timing footer decorator
- [ ] First-run onboarding + `~/.devflow/config.json` + `config reset-onboarding`
- [ ] `devflow menu` fuzzy command palette showing the raw command before running
- [ ] Rich-styled, categorized `--help`
- [ ] `devflow cloud connect` wizard (Supabase / Atlas / Firebase)
- [ ] `devflow cloud status | test | disconnect`
- [ ] Supabase support (pooled + direct URLs, Alembic on direct)
- [ ] MongoDB Atlas support (`mongodb+srv://` validation)
- [ ] Firebase support + new `templates/firestore/` 5-layer set + migrate blocked
- [ ] Fallback engine: probe, CLOUD/DEGRADED/RECOVERED modes
- [ ] Durable write queue + idempotent replay + conflict file (no silent overwrite)
- [ ] `devflow cloud fallback status | sync | enable | disable`
- [ ] `X-DevFlow-Mode` header + `202` on queued writes
- [ ] `env validate` + `deploy checklist` cloud/fallback checks
- [ ] `db switch` recognizes cloud provider names
- [ ] 3 new `guide` pages (cloud, fallback, menu)
- [ ] Updated `README.md`
- [ ] `ruff check` 0 errors, `mypy` 0 errors, `bandit -ll` 0 high severity
- [ ] Test coverage for all new code ≥ 80%

---

## 9. Out of Scope for Phase 5

- VS Code extension, plugin system, cloud sync, Textual TUI, landing page, license keys (Phase 6+ candidates).
- Migrating Phase 1–4 command output to the new theme (future cleanup phase).
- Multi-region cloud replication or write-write conflict resolution beyond the conflict file.

*Do not build any of the above during Phase 5.*
