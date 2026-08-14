# Kaira ⚡ — Monitoring Usage Guide

> Every command in the monitoring phase, what it writes, what it does not touch,
> and where the numbers come from.
>
> **Version:** v0.1.0 · **In-CLI equivalent:** `kaira guide monitor`

---

## Contents

1. [The 60-second version](#the-60-second-version)
2. [Command reference](#command-reference)
3. [What `monitor init` writes](#what-monitor-init-writes)
4. [Routes you get](#routes-you-get)
5. [The mini dashboard](#the-mini-dashboard)
6. [Kaira-native panels](#kaira-native-panels)
7. [Structured logs](#structured-logs)
8. [Third-party providers](#third-party-providers)
9. [Environment variables](#environment-variables)
10. [Docker](#docker)
11. [Scope, limits, and honest caveats](#scope-limits-and-honest-caveats)
12. [Troubleshooting](#troubleshooting)

---

## The 60-second version

```bash
# 1. Scaffold metrics + probes into your project (prompts before touching main.py)
kaira monitor init

# 2. Install the one new dependency it added to requirements.txt
pip install -r requirements.txt

# 3. Start the app
kaira run

# 4. See what is configured and what is actually running
kaira monitor status
```

You now have:

| Route | What it answers |
|---|---|
| `GET /metrics` | Prometheus exposition — counts, latency histogram, errors |
| `GET /healthz` | Is the process alive? |
| `GET /readyz` | Can this instance serve traffic? |

Your existing `GET /health` is **unchanged**.

Want the visual layer too:

```bash
kaira monitor init --dashboard --auth token   # writes a token into .env
# then set KAIRA_MONITOR_ENABLED=true in .env and restart
```

Open `http://127.0.0.1:8000/_kaira/monitor` with the bearer token from `.env`.

---

## Command reference

### `kaira monitor init`

Scaffolds the monitoring surface. **Nothing happens in your project until you run
this**, and it never overwrites a file you have edited without showing you the
diff first.

```bash
kaira monitor init                             # Tier 1: metrics + probes
kaira monitor init --dashboard --auth token    # + dashboard, bearer token gate
kaira monitor init --dashboard --auth reuse    # + dashboard, your own auth guard
kaira monitor init --force                     # overwrite changed files, no prompt
kaira monitor init --quiet                     # non-interactive (CI)
```

| Flag | Meaning |
|---|---|
| `--dashboard` | Also scaffold the self-hosted mini dashboard (Tier 2). |
| `--auth reuse\|token` | How the dashboard is protected. Required with `--dashboard` in non-interactive mode; prompted for otherwise. There is no `public`. |
| `--force` | Overwrite changed files without the diff/confirm prompt. |
| `--quiet` | Never prompt. Applies changes and skips the "Next Steps" panel. |

**Idempotent.** Running it twice changes nothing the second time — imports and
`include_router` calls are not duplicated.

`--auth reuse` requires `auth/dependencies.py` to exist. Without it the command
stops and points you at `kaira auth generate jwt` rather than generating a page
with no gate.

---

### `kaira monitor status`

Two halves, deliberately separate: what is **on disk** (a static fact) and what
the **running process** reports (a live one). A project can be fully scaffolded
and still reporting nothing because it was never restarted.

```bash
kaira monitor status
kaira monitor status --url http://127.0.0.1:9000
```

```
  configured · my-api
  --------------------------------------------
   metrics       ✅ /metrics
   probes        ✅ /healthz  /readyz
   dashboard     /_kaira/monitor · auth: token · off (KAIRA_MONITOR_ENABLED not true)
   json logs     ✅ KAIRA_LOG_FORMAT=json
   provider      none

  live · http://127.0.0.1:8000
  --------------------------------------------
  ✓ application    reachable via dashboard
    requests       1,204
    error rate     0.17%  (2 errors)
    latency        p50 8.1ms · p95 42.0ms · p99 190.4ms
    scope          pid 51221 · single process
                   Under multiple workers this is one worker's view, not an aggregate.
  ·  snapshot      20260814T094512Z.json
  → kaira monitor diff --since yesterday
```

Every successful live check **writes a snapshot** to `.kaira/monitor/`. That is
what `kaira monitor diff` later compares.

---

### `kaira monitor watch`

A terminal-resident process that polls live metrics and fires an alert when a
threshold trips. The default alert path needs no account and no service: the
machine you are sitting at tells you.

```bash
kaira monitor watch                            # defaults: >5% errors, >1000ms p95
kaira monitor watch --error-rate 0.02 --p95 500
kaira monitor watch --interval 30
kaira monitor watch --once                     # single poll, then exit (CI)
```

| Flag | Default | Meaning |
|---|---|---|
| `--url` | `http://127.0.0.1:8000` | Base URL of the running app. |
| `--interval` | `10` | Seconds between polls. |
| `--error-rate` | `0.05` | Alert above this error rate (`0.05` = 5%). |
| `--p95` | `1000` | Alert above this p95 latency, in ms. |
| `--once` | off | Poll a single time and exit. |

```
  watch · http://127.0.0.1:8000
  --------------------------------------------
    interval       10s
    thresholds     error rate > 5.0%  ·  p95 > 1000ms
    webhook        https://hooks.slack.com/***

  09:45:12  ✅  340 reqs  0.00% errors  p95 41.2ms
  09:45:22  ✅  361 reqs  0.28% errors  p95 44.9ms
  09:45:32  ❌  380 reqs  9.21% errors  p95 1841.0ms
      error rate 9.21% > 5.00%
      p95 1841ms > 1000ms
```

**Alerts fire on the transition into a breach, not on every poll.** A threshold
that stays tripped for an hour is one problem, not 360 notifications.

**Optional webhook.** Set `KAIRA_MONITOR_WEBHOOK_URL` and breaches are also
POSTed to Discord or Slack. That URL *is* a credential — whoever has it can post
as the integration — so Kaira only ever prints it masked
(`https://hooks.slack.com/***`).

`watch` also saves a snapshot roughly once a minute, so a long watch session
gives `monitor diff` something to work with.

**Where the data comes from:** the dashboard's JSON endpoint if it is enabled,
otherwise `/metrics` is parsed directly. The alert loop therefore works on a
Tier 1 project with no dashboard at all.

---

### `kaira monitor diff`

Compares two saved snapshots, in the same `+`/`-` visual language as
`kaira sync model --dry-run` and `kaira docker sync --dry-run`.

```bash
kaira monitor diff                        # defaults to --since yesterday
kaira monitor diff --since week
kaira monitor diff --since hour
kaira monitor diff --since 2026-08-01T09:00:00Z
```

Accepted `--since` values: `now`, `hour`, `today`, `yesterday`, `week`, or any
ISO-8601 timestamp.

```
  snapshots · since yesterday
  --------------------------------------------
    baseline       20260813T091500Z.json
    latest         20260814T094512Z.json

  change
  --------------------------------------------
  + requests     1200 → 2400
  + errors       4 → 61
  + error rate   0.33% → 2.54%
  = p50          8
  + p95          42ms → 610ms
  + p99          190ms → 1840ms

  routes · by p95
  --------------------------------------------
  + GET /api/v1/orders  120.0ms → 980.0ms
  - GET /api/v1/users   61.0ms → 44.0ms

  between · what changed in the project
  --------------------------------------------
  · kaira migrate run   2026-08-13T22:14:03Z
```

Green is better, red is worse — and the direction is metric-aware: more requests
is good, more errors is not.

Snapshots only reach as far back as you have been looking. They are written by
`monitor status` and by `monitor watch`; nothing is collected in the background.

---

## What `monitor init` writes

| File | Tier | Purpose |
|---|---|---|
| `core/metrics.py` | 1 | Prometheus counters/histogram + the in-memory rolling window |
| `middleware/metrics.py` | 1 | Per-request instrumentation |
| `routers/probes_router.py` | 1 | `/healthz`, `/readyz`, `/metrics` |
| `core/monitor_dashboard.py` | 2 | The dashboard's HTML (self-contained) |
| `routers/monitor_router.py` | 2 | `/_kaira/monitor` + `/_kaira/monitor/data`, auth-gated |

It also:

- Splices imports, `register_metrics_middleware(app)` and the `include_router`
  calls into `main.py` — **through the diff/confirm prompt**, never silently.
- Adds `prometheus-client>=0.20.0` to `requirements.txt`.
- Regenerates `core/logger.py` so it understands `KAIRA_LOG_FORMAT=json` (again,
  diff first — you see exactly what changes).
- With `--dashboard`: writes `KAIRA_MONITOR_ENABLED=false` and, for the token
  strategy, a generated `KAIRA_MONITOR_TOKEN` into every `.env*` file.
- Records the feature flags in `.kaira.json` and offers a Docker re-sync.

### What it will not do

- **It does not modify `/health`.** Phase 4 owns that route. Docker's
  `HEALTHCHECK` and your deployment platform's probe keep working untouched —
  there is a regression test asserting the `health_check` function is
  byte-identical before and after.
- **It does not reorder middleware.** `register_security_middleware(app)` stays
  first. The metrics middleware is registered *after* it, which — because
  Starlette applies user middleware outermost-last — wraps it rather than
  displacing it.
- **It does not time your requests twice.** The security middleware already
  computes the duration for `X-Response-Time`; the metrics middleware reads that
  header back. One stopwatch per request.
- **It does not write log files.** Ever.
- **It does not touch a project that never runs it.**

---

## Routes you get

### `GET /metrics`

Prometheus exposition. Unauthenticated, for the same reason `/health` is: a
scraper cannot present credentials. Rate-limited at `300/minute` so a 1-second
scrape interval never 429s.

```
kaira_requests_total{method="GET",path="/api/v1/users/{uuid}",status="200"} 1204.0
kaira_request_duration_seconds_bucket{le="0.1",method="GET",path="/api/v1/users/{uuid}"} 1180.0
kaira_errors_total{method="GET",path="/api/v1/users/{uuid}",status="500"} 2.0
```

**Labels use the route template, never the real path.** `/api/v1/users/{uuid}`,
not `/api/v1/users/3f8c…`. A label per resource id is unbounded cardinality — it
exhausts the metrics backend long before it tells you anything useful. Requests
that match no route at all collapse to a single `unmatched` label, so someone
spraying random URLs cannot inflate the label set either.

No request bodies, no headers, no query strings, no user identifiers. Counts and
timings only.

### `GET /healthz` — liveness

```json
{ "status": "alive" }
```

The cheapest endpoint in the application: no database, no cache, no disk. If it
answers, the process is worth keeping. If it does not, restarting is the correct
remedy — which is exactly the decision a liveness probe is allowed to make.

### `GET /readyz` — readiness

```json
{ "status": "ready", "dependencies": { "database": "ok", "cache": "ok" } }
```

Runs the same dependency checks `/health` already performs, and returns **503**
when any of them is unavailable — which removes the instance from the
load-balancer pool without restarting it.

Coarse states only. Never a connection string, never an exception message; the
reason is in the server log, where it is already written.

**Why the split matters:** with a single `/health` wired to both probes, a
30-second database blip makes liveness fail and your orchestrator kills a
perfectly healthy process — the classic restart loop during a database incident.

### Kubernetes example

```yaml
livenessProbe:
  httpGet: { path: /healthz, port: 8000 }
  periodSeconds: 10
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  periodSeconds: 5
```

Docker's in-image `HEALTHCHECK` still points at `/health` and is not changed by
this phase.

---

## The mini dashboard

`GET /_kaira/monitor` — a single self-contained HTML page styled from Kaira's own
design tokens, polling `GET /_kaira/monitor/data` every 5 seconds.

Shows: uptime, request count, error rate, p50/p95/p99, a per-minute latency
sparkline with request-volume bars, top routes by traffic, top routes by latency,
dependency health, and the Kaira-native panels below.

No external requests. No CDN, no font host, no analytics — the page is served
from inside your application and should not phone anywhere. It respects
`prefers-color-scheme` and `prefers-reduced-motion`, and tells you where the raw
endpoints are if JavaScript is off.

### Why it is not public

`/health` is public because it says almost nothing. This page says which of your
routes are hot, which are failing, how many auth attempts are being rejected, and
how close your database is to its plan limit. That is a map of your system's soft
spots.

So it ships **off**, and it cannot be turned on halfway:

1. `KAIRA_MONITOR_ENABLED=true` must be set, or **both routes return 404** — the
   same answer an unmounted path gives, so probing cannot even confirm the
   feature exists.
2. An auth strategy must have been chosen at scaffold time:

| Strategy | How it gates |
|---|---|
| `reuse` | The project's own `auth.dependencies.get_current_user` runs on both routes. One identity system, not two. |
| `token` | A bearer token matching `KAIRA_MONITOR_TOKEN`, compared in constant time. A token shorter than 24 characters disables the routes entirely rather than pretending to protect them. |

There is no third option. A dashboard scaffolded with no strategy recorded stays
closed, and `kaira monitor status` shouts about it in red.

### Reaching it

```bash
# Token strategy — the token was generated into your .env at init time
curl -H "Authorization: Bearer $KAIRA_MONITOR_TOKEN" \
     http://127.0.0.1:8000/_kaira/monitor/data
```

In a browser, use an extension that sets the header, or switch to `--auth reuse`
so your normal session cookie/JWT works.

### Why `/_kaira/`

Your API owns `/api/v1/*` and your root. A bare `/monitor` would collide the day
someone runs `kaira generate model Monitor`. Nothing Kaira generates mounts
outside the reserved `/_kaira/` prefix without being asked to.

---

## Kaira-native panels

These exist because Kaira owns the model → router pipeline and the command
history. A generic monitoring tool cannot build them — it never saw your model
definitions.

### Model activity

```
Model Activity (last hour)
  User      1,204 reqs   2 errors
  Order       340 reqs   0 errors
  Product      88 reqs  12 errors  ⚠
```

Traffic per *model*, not per URL prefix. Each generated router declares
`KAIRA_MODEL = "User"`, and the middleware reads it. For projects generated
before that constant existed, the router's tag is used instead — so this panel
works without regenerating anything.

### Change markers

`migrate run`, `sync model`, `deploy run` and friends are read from
`.kaira/history.jsonl` — which Kaira has written since Phase 4 — and drawn as
vertical rules on the latency timeline. *"Latency jumped right after this
migration"* becomes visible instead of inferred.

Read-only. This phase adds no logging surface to produce them.

### Self-baseline anomalies

A route is compared **only against its own p95** from previous days, over a
rolling 7-day window. If it runs more than 1.5× its own baseline, it is flagged.

```
Baseline anomalies
  GET /api/v1/orders   980ms now   ·   120ms baseline   ·   8.2×
```

No ML, no external service, no cross-project comparison. A route that is
legitimately slow never trips the flag by being slow — only by being slower than
*it* usually is. Nothing is flagged until a route has at least one completed day
of history.

### Security event feed

Counts the `401`, `403` and `429` responses your auth guard and slowapi already
return. It is a feed, not a detector: no new detection logic, no new surface —
just the events that were already happening, aggregated and timestamped.

### Storage runway

A **periodic** (not per-request) database size query plus a straight-line
projection:

```
database size   412.8 MB
plan limit      1.0 GB
growth          31.2 MB / day
runway          ~19 days
```

The query runs at most once every 15 minutes, so refreshing the dashboard costs
nothing. Set `KAIRA_STORAGE_LIMIT_MB` to declare your plan's ceiling — hosted
databases do not advertise their quota over the wire, so that number has to come
from you. Without it you still get the growth rate, just no date.

The projection says nothing at all until it has two samples to draw a line
through, and it says so rather than guessing.

---

## Structured logs

```bash
KAIRA_LOG_FORMAT=json
```

Switches `core/logger.py`'s existing Loguru sink from the aligned human-readable
format to one JSON object per line — **still on stdout**.

```json
{"timestamp":"2026-08-14T09:45:12.418+00:00","level":"INFO","message":"GET 200 /api/v1/users 8.1ms","logger":"middleware.security","event":"request","method":"GET","path":"/api/v1/users","status":200,"duration_ms":8.1,"request_id":"63cb0206","client":"127.0.0.1"}
```

Request fields are flat at the top level, so a query like `status:500` works
without a nested path.

Default is unchanged: set nothing, and your logs look exactly as they did.

### There is no log file, and there will not be one

Railway, Render, Fly and CloudWatch all ingest logs by capturing the process's
stdout. A JSON *formatter* is the whole job. A log file inside a container is
invisible to the platform collecting stdout, grows until it fills the disk, and
needs rotation config to survive — three problems in exchange for nothing the
platform does not already do better.

Structured mode also never enables Loguru's `diagnose`, which prints local
variable *values* into tracebacks. Those are unacceptable in production already;
embedding them in a machine-readable line that ships to a third-party aggregator
is strictly worse.

---

## Third-party providers

Entirely optional. Nothing in Tiers 1–3 needs a provider account.

```bash
kaira integrate --provider monitor/sentry
kaira integrate --provider monitor/datadog
kaira integrate --provider monitor/newrelic
```

This used to install the SDK and write env keys but never call `init()`. It now
generates `core/monitor_sdk.py` and starts it from your `lifespan` — again,
through the diff/confirm prompt.

### Cost-conscious by default

These are metered services, and the fastest route to a surprise invoice is a
default of "send everything".

| Environment | Trace sample rate |
|---|---|
| `development` | `1.0` |
| `production` | `0.2` |

The value lives in `settings.MONITOR_TRACES_SAMPLE_RATE`, never hardcoded at the
call site, so raising it to full fidelity is a config change.

**Errors are never sampled.** An exception you never see is worse than an
exception you pay a fraction of a cent for.

### Safety

- A missing credential logs one line and the app boots normally. An
  observability tool must never be the reason a service fails to start.
- Sentry is initialised with `send_default_pii=False`. Turning that on ships
  request bodies, headers and user identifiers to a third party — an explicit
  decision, never a generated default.
- The credential is read from `settings` and never logged. The startup line
  reports that the provider is enabled and at what sample rate — not the key.

---

## Environment variables

| Variable | Default | Effect |
|---|---|---|
| `KAIRA_LOG_FORMAT` | `text` | `json` switches the stdout formatter to structured lines. |
| `KAIRA_MONITOR_ENABLED` | `false` | Must be `true` for the dashboard routes to exist at all. |
| `KAIRA_MONITOR_TOKEN` | *(generated)* | Bearer token for the `token` auth strategy. 24-char minimum. |
| `KAIRA_MONITOR_WEBHOOK_URL` | unset | Optional Discord/Slack webhook for `monitor watch`. Always printed masked. |
| `KAIRA_STORAGE_LIMIT_MB` | `0` | Your plan's storage ceiling, so the runway gauge can project a date. |
| `KAIRA_LOG_SKIP_PATHS` | unset | Existing Phase 8 knob — add `/metrics,/healthz,/readyz` to keep probes out of the request log. |

Recommended in a deployed environment:

```bash
KAIRA_LOG_FORMAT=json
KAIRA_LOG_SKIP_PATHS=/health,/healthz,/readyz,/metrics
KAIRA_MONITOR_ENABLED=false
```

---

## Docker

Monitoring adds **no compose service**. There is no Prometheus/Grafana/Loki stack
in this phase, by design — `/metrics` is a scrape target for whatever you already
run, and the dashboard is served by the app itself.

What does change: `kaira docker sync` records monitoring in the compose header
through the same dynamic rendering every other feature uses, so `docker status`
and the generated file agree with `.kaira.json`.

```yaml
# Generated by Kaira from the current project state:
#   database: PostgreSQL · cache: redis · metrics: /metrics
```

`monitor init` offers the re-sync automatically, the same way `cache init` does.

The in-image `HEALTHCHECK` still targets `/health` — unchanged, and covered by a
regression test.

---

## Scope, limits, and honest caveats

### Single worker

**The dashboard's metrics are in-memory and per-process.**

Under one uvicorn worker — development, and small single-container deployments —
they are the whole truth. Under `gunicorn -w 4` you are looking at whichever
worker answered your dashboard request: roughly a quarter of your traffic, not a
quarter-scale copy of it.

`/metrics` has the same property, and there it is fine: a scraper hits every
replica and aggregates them. It is the dashboard's single-process view that would
mislead, so the page says so on its own face, the `/data` payload carries the
caveat in its `scope` field, and `kaira monitor status` repeats it.

Cross-worker aggregation needs a shared backend — Redis-aggregated counters, or
`prometheus_client`'s multiprocess mode. That is a natural next step and is
deliberately not built here.

### Restarts reset the window

The rolling window and the anomaly baselines live in process memory. A restart
clears them, and the baseline needs a full day of traffic before it can flag
anything. Prometheus scraping is the durable path; the dashboard is the
right-now path.

### Snapshots are opt-in samples

`monitor diff` compares files written by `monitor status` and `monitor watch`.
Nothing collects them in the background, so a diff reaches back exactly as far as
you have been looking.

### Explicitly not in this phase

- A full `docker-compose.monitoring.yml` (Prometheus + Grafana + Loki)
- Pre-built Grafana dashboard templates
- OpenTelemetry / distributed tracing / OTLP export
- Prometheus Alertmanager rule templates
- A custom business-metrics authoring API
- Log file sinks or rotation
- A multi-worker shared metrics backend
- Kubernetes manifests / Helm charts

---

## Troubleshooting

**`/metrics` returns an almost-empty body**
`prometheus_client` is not installed. The app boots without it on purpose —
losing `/metrics` is an inconvenience, refusing to start is an outage. Run
`pip install -r requirements.txt`.

**`/_kaira/monitor` returns 404**
Either `KAIRA_MONITOR_ENABLED` is not `true`, or the token is shorter than 24
characters, or no auth strategy was recorded. All three are answered with 404 by
design so probing cannot confirm the route exists. `kaira monitor status` tells
you which one it is.

**`/_kaira/monitor` returns 401**
The route exists and you are not authorised. Check the bearer token, or your
session if you chose `--auth reuse`.

**`monitor status` says "not reachable"**
The app is not running, or it is on a different port. Start it with `kaira run`,
or pass `--url`.

**The model activity panel says `unattributed`**
The request did not match a generated router — the root route, a probe, or a
hand-written endpoint. Regenerating routers adds the explicit `KAIRA_MODEL`
constant, but the router tag already covers generated routers either way.

**Anomalies never appear**
The baseline needs at least one completed day of traffic for that route, and a
restart clears it. This is working as intended: flagging against an empty
baseline would flag everything on the first request.

**`monitor init` said main.py was left unchanged**
Your `main.py` no longer has the anchors Kaira generated (`register_exception_handlers(app)`
and the `# [ROUTER_REGISTRATION]` marker). It prints the exact two lines to add
rather than editing a restructured file on a guess.

**Docker keeps reporting drift after `monitor init`**
Run `kaira docker sync`. The compose header records enabled features, and metrics
is now one of them.

---

## See also

- `kaira guide monitor` — the same material, in the terminal
- `docs/MONITORING_STATUS.md` — the gap analysis this phase was built from
- `README.md` → *Monitoring (`kaira monitor`)*
