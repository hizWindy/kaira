# Kaira ⚡ — Docker Phase: Manual Test Guide

> Walks through every command added or changed in the Docker Hardening &
> Modernization phase, with copy-pasteable commands and the output to expect.
> Run top to bottom in a scratch directory — nothing here touches a real project.

**Covers:** `kaira docker init / sync / build / run / up / down / status / scan`,
the dynamic compose registry (cache / tasks / search / database), and the
auto-sync hook wired into `cache init`, `task init`, `integrate`, `db switch`,
and `cloud connect`.

**Requires:** Docker Desktop (or a Docker daemon) running. Commands that only
touch generated files (`init`, `sync`) work without Docker running; `build`,
`run`, `up`, `down`, `status`, `scan` need the daemon.

---

## 0. Setup

```bash
mkdir kaira-docker-test && cd kaira-docker-test
```

Create a minimal `.kaira.json` by hand (or use `kaira init` instead — see §9):

```bash
cat > .kaira.json <<'EOF'
{"output_dir": ".", "db_type": "postgresql"}
EOF
printf 'fastapi\nuvicorn\n' > requirements.txt
```

Add a real `main.py` so the container has something to boot and a `/health`
route for the Dockerfile's `HEALTHCHECK` to hit:

```bash
cat > main.py <<'EOF'
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
EOF
```

---

## 1. `kaira docker init`

```bash
kaira docker init --with-compose --python 3.12
```

**Expect:**

```
  docker init · kaira-docker-test
  --------------------------------------------
       python         3.12.8-slim
       database       PostgreSQL
       services       PostgreSQL
  [ok] Dockerfile     new
  [ok] .dockerignore  new
  [ok] docker-compose.yml new
  [ok] docker-compose.prod.yml new
╭────────────────────── Next Steps ──────────────────────╮
│   1. Build the image:  kaira docker build              │
│   2. Start the stack:  kaira docker up                 │
│   3. Scan for CVEs:  kaira docker scan                 │
│   4. Re-sync after project changes:  kaira docker sync │
╰────────────────────────────────────────────────────────╯
 Docker scaffold ready · 4 files generated · 0 warnings
```

**Checklist:**
- [ ] `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `docker-compose.prod.yml` all exist
- [ ] `.kaira.json` now has `"docker_enabled": true`, `"docker_compose": true`, `"docker_python": "3.12.8"`
- [ ] Dockerfile pins `ARG PYTHON_VERSION=3.12.8` (full patch, never `latest` or minor-only)
- [ ] Dockerfile's builder stage installs `gcc libpq-dev` (Postgres build deps)
- [ ] `docker-compose.yml` has `app` + `db` services, no `version:` key

### 1a. Rejecting an unsupported Python version

```bash
kaira docker init --python 3.7 --force
```

**Expect:** a smart error — exit code 1, message naming `3.12` as a valid option, no files touched.

### 1b. Dockerfile-only (no `--with-compose`)

```bash
rm -f docker-compose*.yml
kaira docker init --force
```

**Expect:** only `Dockerfile` and `.dockerignore` are (re)written — no compose files appear.

Restore compose for the rest of this guide:

```bash
kaira docker init --with-compose --force
```

---

## 2. `kaira docker sync`

### 2a. Clean project reports up to date

```bash
kaira docker sync
```

**Expect:**

```
  docker sync · kaira-docker-test
  --------------------------------------------
       database       PostgreSQL
       services       PostgreSQL
   Docker files are up to date.
 Already in sync · 0 files generated · 0 warnings
```

- [ ] Nothing written, exit code 0

### 2b. Drift after a manual state edit

```bash
python -c "
import json
d = json.load(open('.kaira.json'))
d['cache_enabled'] = True
d['task_enabled'] = True
d['search_provider'] = 'meilisearch'
json.dump(d, open('.kaira.json', 'w'))
"
kaira docker sync --dry-run
```

**Expect:** a diff panel for `docker-compose.yml` and `docker-compose.prod.yml`
adding `redis`, `worker`, and `search` services — and **nothing is written**
(check `git diff` / file mtimes if unsure).

- [ ] Dry run shows the diff but the compose files are unchanged on disk

### 2c. Applying the sync

```bash
kaira docker sync --force
```

**Expect:** both compose files rewritten; `docker-compose.yml` now contains
`app, db, redis, worker, search`.

```bash
python -c "
import yaml
print(sorted(yaml.safe_load(open('docker-compose.yml'))['services']))
"
```

- [ ] Prints `['app', 'db', 'redis', 'search', 'worker']`
- [ ] Re-running `kaira docker sync` immediately after reports "up to date" again

### 2d. Sync with no Dockerfile

```bash
mkdir ../no-docker-project && cd ../no-docker-project
echo '{"output_dir": "."}' > .kaira.json
kaira docker sync
cd ../kaira-docker-test
```

**Expect:** smart error — "This project has no generated Dockerfile to sync,"
fix command `kaira docker init --with-compose`, exit code 1.

---

## 3. `kaira docker build`

```bash
kaira docker build --tag kaira-test-image
```

**Expect (first build, ~3–4 min while apt/pip resolve):**

```
  docker build · kaira-test-image
  --------------------------------------------
... building kaira-test-image
  [ok] image          kaira-test-image
       size           <some MB>
 Image built · 0 warnings
```

- [ ] Exit code 0
- [ ] `docker images kaira-test-image` shows the tag

### 3a. Verify hardening inside the image

```bash
docker run --rm --entrypoint sh kaira-test-image -c "id"
```

**Expect:** `uid=... gid=... groups=...` for user **`app`**, not root.

```bash
docker run --rm --entrypoint sh kaira-test-image -c \
  "python -c 'import fastapi; print(fastapi.__file__)'"
```

**Expect:** path under `/home/app/.local/...` — proof the `--user` pip install
landed in the runtime stage correctly.

### 3b. Verbose mode and a deliberate failure

```bash
kaira docker build --tag kaira-test-image --verbose
```

**Expect:** full raw Docker build log streamed instead of the spinner/summary.

```bash
mv requirements.txt requirements.txt.bak
kaira docker build --tag kaira-test-fail
mv requirements.txt.bak requirements.txt
```

**Expect:** build fails fast with a smart error naming `requirements.txt` as
the problem, not a raw Docker stack trace.

---

## 4. `kaira docker run`

```bash
kaira docker run --tag kaira-test-image --port 18000
```

**Expect:** container starts detached; footer prints `http://localhost:18000`.

```bash
curl -s http://localhost:18000/health
```

**Expect:** `{"status":"ok"}`

### 4a. Graceful shutdown (exec-form CMD + `--init`)

```bash
CID=$(docker ps -q --filter ancestor=kaira-test-image | head -1)
time docker stop "$CID"
```

**Expect:** stops in ~1 second, **not** the ~10s timeout-then-SIGKILL you'd see
if `CMD` were shell-form and swallowing `SIGTERM`.

### 4b. Healthcheck reports healthy

```bash
docker run -d --name kaira-hc-test --init -p 18001:8000 kaira-test-image
sleep 20
docker inspect kaira-hc-test --format '{{.State.Health.Status}}'
docker stop kaira-hc-test && docker rm kaira-hc-test
```

**Expect:** `healthy`

- [ ] Container runs as non-root
- [ ] `--read-only` + `--security-opt no-new-privileges` are present in the `docker run` invocation (check with `docker inspect $CID --format '{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.SecurityOpt}}'`)

---

## 5. `kaira docker up` / `kaira docker down`

### 5a. Dev stack

```bash
kaira docker up --build
```

**Expect:** streams logs in the foreground (dev is *not* detached by default).
Press `Ctrl+C` — it should stop cleanly with no traceback.

Run it detached instead to inspect status:

```bash
kaira docker up --detach
kaira docker status
```

**Expect `status`:** a table with `app`, `db` (and `redis`/`worker`/`search` if
you kept the drifted state from §2c), each showing `running` and a health
column; image name + size; database + volume facts. **No connection strings
or secrets anywhere in the output.**

```bash
kaira docker down
```

**Expect:** containers stopped, network removed. `docker ps` shows nothing
from this project.

### 5b. `--volumes` requires typed confirmation

```bash
kaira docker up --detach
kaira docker down --volumes
```

**Expect:** a prompt asking you to type the project directory name
(`kaira-docker-test`) to confirm. Typing anything else (or pressing Enter)
aborts with **no volumes destroyed**.

```bash
docker volume ls | grep kaira_docker_test
```

- [ ] Volumes still exist after an aborted confirmation
- [ ] Volumes are gone after confirming with the correct typed name

### 5c. Production requires typed confirmation, defaults to detached

```bash
kaira docker up --prod
```

**Expect:** a typed-confirmation prompt (type the project directory name)
before anything starts. On confirmation, the stack starts **detached** by
default (unlike dev).

```bash
kaira docker status --prod
kaira docker down --prod
```

### 5d. Pre-flight checks

```bash
docker context use default >/dev/null 2>&1  # ensure a normal context
# Simulate a missing compose file:
mv docker-compose.yml docker-compose.yml.bak
kaira docker up
mv docker-compose.yml.bak docker-compose.yml
```

**Expect:** smart error pointing at `kaira docker init --with-compose` —
never a raw "file not found."

---

## 6. `kaira docker status` (no containers running)

```bash
kaira docker down 2>/dev/null
kaira docker status
```

**Expect:**

```
  docker status · kaira-docker-test
  --------------------------------------------
  -    containers     none running
  -> kaira docker up
 No containers running
```

- [ ] Exit code 0, not an error — an empty stack is a normal state

---

## 7. `kaira docker scan`

Requires one of `docker scout` (bundled with Docker Desktop), `trivy`, or
`grype` on PATH. The command auto-detects whichever is present, in that order.

```bash
kaira docker scan --tag kaira-test-image --fix
```

**Expect:** a severity-sorted table (`CRITICAL`/`HIGH` red, `MEDIUM` yellow,
`LOW` muted) with a **Fixed in** column, a totals line, and:

```bash
echo "exit code: $?"
```

- [ ] Exit code **1** if any `HIGH`/`CRITICAL` finding exists — this is the CI gate
- [ ] Exit code **0** on a clean scan or medium/low only

### 7a. Local-only by default

```bash
kaira docker scan --tag some/image-you-dont-have-locally
```

**Expect:** smart error — "not present locally," suggests `--remote` or
`kaira docker build`. **No pull is attempted.**

```bash
kaira docker scan --tag some/image-you-dont-have-locally --remote
```

**Expect:** this time it's allowed to pull and scan.

### 7b. No scanner installed

Temporarily rename/hide `docker`, `trivy`, and `grype` from PATH (or test in
an environment without them) and re-run `kaira docker scan`.

**Expect:** smart error listing install hints for all three scanners — not a
Python traceback.

---

## 8. Dynamic behavior — the actual point of this phase

Every check below confirms Docker **reacts** to project state instead of
staying frozen at whatever `init` produced.

| Change | Command | Expect in `docker-compose.yml` after sync |
|---|---|---|
| Enable Redis cache | `kaira cache init` | `redis` service appears |
| Enable Celery | `kaira task init` | `worker` **and** `redis` appear (shared broker) |
| Add search | `kaira integrate --provider search/elasticsearch` | `search` service (Elasticsearch image) appears |
| Switch database | `kaira db switch mongodb` | `db` service becomes Mongo; Dockerfile drops `libpq-dev`, no `apt-get` layer at all |
| Switch to a cloud DB | `kaira db switch supabase` (routes to `cloud connect`) | `db` service **disappears**; Dockerfile keeps `libpq-dev` (Supabase is Postgres-compatible) |

Try one end to end:

```bash
kaira cache init --quiet   # --quiet: prints a hint instead of prompting
```

**Expect:** `core/cache.py` generated, then a muted line:
`Docker configuration is out of sync (...). Run: kaira docker sync`

```bash
kaira docker sync --force
python -c "
import yaml
print('redis' in yaml.safe_load(open('docker-compose.yml'))['services'])
"
```

- [ ] Prints `True`

Now try it **without** `--quiet` in an interactive shell:

```bash
kaira task init
```

**Expect:** after Celery scaffolds, an interactive prompt:
`Docker configuration is out of sync ... Regenerate? [y/n]` — answering `y`
regenerates immediately; `n` leaves the files untouched and reminds you to run
`kaira docker sync` manually.

---

## 9. End-to-end via `kaira init --docker`

A second, independent path — confirms the project-scaffold flow and the
`docker` command group produce identical output for the same state.

```bash
cd ..
kaira init demo-project --db postgresql --auth none --docker --ci none \
  --profile scale --yes
cd demo-project
kaira docker sync
```

**Expect:** `kaira docker sync` reports **"Docker files are up to date"**
immediately — a freshly scaffolded project must never look drifted against
itself.

- [ ] `.kaira.json` has `docker_enabled: true`, `docker_compose: true`, `docker_python` set
- [ ] `docker-compose.yml`'s `POSTGRES_DB` default matches the project's slug (hyphens converted to underscores, e.g. `demo_project`)

---

## 10. CI templates carry the same scan gate

```bash
cd ..
mkdir ci-test && cd ci-test
echo '{"output_dir": "."}' > .kaira.json
kaira ci generate --platform github
kaira ci generate --platform gitlab
kaira ci generate --platform bitbucket
grep -n "trivy" .github/workflows/deploy.yml .gitlab-ci.yml bitbucket-pipelines.yml
```

**Expect:** each generated pipeline has a Trivy scan step between build and
push, configured to fail the pipeline (`exit-code: '1'` / `--exit-code 1`) on
`HIGH`/`CRITICAL` — the same threshold `kaira docker scan` uses locally.

---

## 11. Cleanup

```bash
cd ..
kaira docker down --volumes --force -C kaira-docker-test 2>/dev/null
docker rmi -f kaira-test-image kaira-test-fail 2>/dev/null
docker rm -f kaira-hc-test 2>/dev/null
rm -rf kaira-docker-test no-docker-project demo-project ci-test
```

---

## Result Summary

Copy this table and fill it in as you go:

| # | Area | Command(s) | Pass? |
|---|---|---|---|
| 1 | `docker init` (scaffold + `--python` validation) | §1, §1a, §1b | ☐ |
| 2 | `docker sync` (clean / dry-run / apply / no-Dockerfile) | §2a–2d | ☐ |
| 3 | `docker build` (image, hardening, verbose, smart error) | §3, §3a, §3b | ☐ |
| 4 | `docker run` (hardened defaults, graceful stop, healthcheck) | §4, §4a, §4b | ☐ |
| 5 | `docker up` / `down` (dev, prod, `--volumes` typed confirm) | §5a–5d | ☐ |
| 6 | `docker status` (empty state) | §6 | ☐ |
| 7 | `docker scan` (severity table, exit code, local-only, no scanner) | §7, §7a, §7b | ☐ |
| 8 | Dynamic sync (cache / task / search / db switch / auto-prompt) | §8 | ☐ |
| 9 | `kaira init --docker` parity with `kaira docker init` | §9 | ☐ |
| 10 | CI templates include the Trivy gate | §10 | ☐ |
