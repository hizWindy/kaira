"""Guide command module containing beautiful, copy-pasteable CLI tutorials and tips."""

from __future__ import annotations


import typer
from rich.panel import Panel

from devflow.console import console

app = typer.Typer(help="Interactive guides for all DevFlow operations.")


def print_guide_panel(title: str, content: str, tip: str) -> None:
    """Helper to display guide content with standard Rich layout."""
    full_text = f"{content.strip()}\n"
    if tip:
        full_text += f"\n[bold cyan]Tip:[/bold cyan] {tip}"

    console.print(
        Panel(
            full_text,
            title=f"⚡ DevFlow — Guide: {title}",
            border_style="cyan",
            expand=False,
        )
    )


@app.callback(invoke_without_command=True)
def guide_main(
    ctx: typer.Context,
) -> None:
    """Show list of available guides when no topic is provided."""
    if ctx.invoked_subcommand is None:
        content = (
            "Available guides:\n\n"
            "  [bold cyan]devflow guide init[/bold cyan]              Project initialization\n"
            "  [bold cyan]devflow guide generate[/bold cyan]          Model & layer generation\n"
            "  [bold cyan]devflow guide auth[/bold cyan]              Authentication setup\n"
            "  [bold cyan]devflow guide migrate[/bold cyan]           Database migrations\n"
            "  [bold cyan]devflow guide security[/bold cyan]          Security commands\n"
            "  [bold cyan]devflow guide test[/bold cyan]              Test generation & running\n"
            "  [bold cyan]devflow guide docker[/bold cyan]            Docker setup\n"
            "  [bold cyan]devflow guide ci[/bold cyan]                CI/CD pipeline setup\n"
            "  [bold cyan]devflow guide env[/bold cyan]               Environment management\n"
            "  [bold cyan]devflow guide db[/bold cyan]                Database configuration\n"
            "  [bold cyan]devflow guide config[/bold cyan]            DevFlow configuration\n"
            "  [bold cyan]devflow guide deps[/bold cyan]              Dependency management\n"
            "  [bold cyan]devflow guide cache[/bold cyan]             Redis caching\n"
            "  [bold cyan]devflow guide task[/bold cyan]              Background tasks (Celery)\n"
            "  [bold cyan]devflow guide integrate[/bold cyan]         Third-party integrations\n"
            "  [bold cyan]devflow guide api[/bold cyan]               API testing & client generation\n"
            "  [bold cyan]devflow guide quality[/bold cyan]           Code quality tools\n"
            "  [bold cyan]devflow guide deploy[/bold cyan]            Deployment checklist & configs\n"
            "  [bold cyan]devflow guide flags[/bold cyan]             Feature flags\n"
            "  [bold cyan]devflow guide health-endpoint[/bold cyan]   Health monitoring endpoint\n\n"
            "  [bold magenta]── Phase 5 ──────────────────────────────────[/bold magenta]\n"
            "  [bold cyan]devflow guide cloud[/bold cyan]             Cloud database setup (Supabase/Atlas/Firebase)\n"
            "  [bold cyan]devflow guide fallback[/bold cyan]          Cloud → local fallback mode\n"
            "  [bold cyan]devflow guide menu[/bold cyan]              Using the interactive command palette\n"
            "  [bold magenta]── Phase 5.5 ────────────────────────────────[/bold magenta]\n"
            "  [bold cyan]devflow guide sync[/bold cyan]              Cascade model field changes across layers"
        )
        print_guide_panel("Index", content, "Run any guide for examples and usage.")


@app.command("init")
def guide_init() -> None:
    """Guide for project initialization."""
    content = (
        "Initialize a new FastAPI project:\n\n"
        "[bold green]Basic:[/bold green]\n"
        "  devflow init myproject\n\n"
        "[bold green]With database flag:[/bold green]\n"
        "  devflow init myproject --db postgresql\n"
        "  devflow init myproject --db mysql\n"
        "  devflow init myproject --db mongodb\n"
        "  devflow init myproject --db sqlite\n\n"
        "[bold green]With auth flag:[/bold green]\n"
        "  devflow init myproject --auth jwt\n"
        "  devflow init myproject --auth oauth2\n"
        "  devflow init myproject --auth api-key\n\n"
        "[bold green]With all flags:[/bold green]\n"
        "  devflow init myproject \\\n"
        "    --db postgresql \\\n"
        "    --auth jwt \\\n"
        "    --docker \\\n"
        "    --ci github"
    )
    print_guide_panel(
        "init", content, "Run devflow init without flags for interactive wizard."
    )


@app.command("generate")
def guide_generate() -> None:
    """Guide for model & layer generation."""
    content = (
        "Generate all 5 layers for a model:\n"
        "  devflow generate model User \\\n"
        '    --fields "username:str, email:str, age:int"\n\n'
        "Generate with tier:\n"
        "  devflow generate model User \\\n"
        '    --fields "username:str, email:str" \\\n'
        "    --tier simple\n\n"
        "  devflow generate model User \\\n"
        '    --fields "username:str, email:str" \\\n'
        "    --tier full\n\n"
        "Add relationships after generation:\n"
        "  devflow add relation Post --has-one User\n"
        '  devflow add relation Post --has-many Comment --cascade "all, delete-orphan"\n'
        "  devflow add relation Post --many-to-many Tag\n\n"
        "Generate single layer only:\n"
        "  devflow generate router User\n"
        "  devflow generate service User\n"
        "  devflow generate schema User\n"
        "  devflow generate repository User\n\n"
        "Bulk generate from JSON:\n"
        "  devflow generate bulk models.json\n\n"
        "Example models.json:\n"
        "  [\n"
        "    {\n"
        '      "name": "User",\n'
        '      "fields": {\n'
        '        "username": "str",\n'
        '        "email": "str",\n'
        '        "age": "int"\n'
        "      }\n"
        "    },\n"
        "    {\n"
        '      "name": "Post",\n'
        '      "fields": {\n'
        '        "title": "str",\n'
        '        "body": "str"\n'
        "      },\n"
        '      "relations": [\n'
        "        {\n"
        '          "type": "many-to-one",\n'
        '          "target": "User"\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]"
    )
    print_guide_panel(
        "generate", content, "Model names must be PascalCase. Fields are snake_case."
    )


@app.command("auth")
def guide_auth() -> None:
    """Guide for authentication setup."""
    content = (
        "Generate authentication layer:\n"
        "  devflow auth generate --type jwt\n"
        "  devflow auth generate --type oauth2\n"
        "  devflow auth generate --type api-key\n\n"
        "Add auth guard to a router:\n"
        "  devflow auth add-guard users\n"
        "  devflow auth add-guard products\n"
        "  devflow auth add-guard orders\n\n"
        "Full auth setup flow:\n"
        "  1. devflow auth generate --type jwt\n"
        "  2. devflow auth add-guard users\n"
        "  3. devflow auth add-guard products\n"
        "  4. devflow audit security"
    )
    print_guide_panel(
        "auth", content, "Always run devflow audit security after adding guards."
    )


@app.command("migrate")
def guide_migrate() -> None:
    """Guide for database migrations."""
    content = (
        "Database migration operations (relational databases only):\n\n"
        "Initialize Alembic:\n"
        "  devflow migrate init\n\n"
        "Create migration revision:\n"
        '  devflow migrate make "add users table"\n\n'
        "Run pending migrations:\n"
        "  devflow migrate run\n\n"
        "Rollback last migration:\n"
        "  devflow migrate rollback"
    )
    print_guide_panel(
        "migrate",
        content,
        "MongoDB does not use migrations or support migration commands.",
    )


@app.command("security")
def guide_security() -> None:
    """Guide for security auditing."""
    content = (
        "Security audit checks for all routes, schemas, and configurations:\n\n"
        "Run full project security audit:\n"
        "  devflow audit security\n\n"
        "List registered app routes:\n"
        "  devflow audit routes\n\n"
        "Find unused/unregistered app components:\n"
        "  devflow audit unused"
    )
    print_guide_panel(
        "security",
        content,
        "Security is applied by default starting from project initialization.",
    )


@app.command("test")
def guide_test() -> None:
    """Guide for testing."""
    content = (
        "Generate and run tests:\n\n"
        "Generate tests for all models:\n"
        "  devflow test generate --all\n\n"
        "Generate tests for a specific model:\n"
        "  devflow test generate User\n\n"
        "Run test suite with Rich coverage report:\n"
        "  devflow test run"
    )
    print_guide_panel("test", content, "Unit tests are run using pytest-cov package.")


@app.command("docker")
def guide_docker() -> None:
    """Guide for Docker configuration."""
    content = (
        "Docker environment setup:\n\n"
        "Initialize Docker config files:\n"
        "  devflow docker init --with-compose\n\n"
        "Build application Docker image:\n"
        "  devflow docker build --tag myapp\n\n"
        "Run Docker image locally with environment configuration:\n"
        "  devflow docker run --tag myapp"
    )
    print_guide_panel(
        "docker", content, "Docker run uses security-hardened flags by default."
    )


@app.command("ci")
def guide_ci() -> None:
    """Guide for CI/CD setup."""
    content = (
        "Scaffold pipeline configurations for continuous integration:\n\n"
        "Generate GitHub Actions workflows:\n"
        "  devflow ci generate --platform github\n\n"
        "Generate GitLab CI/CD file:\n"
        "  devflow ci generate --platform gitlab\n\n"
        "Generate Bitbucket Pipelines config:\n"
        "  devflow ci generate --platform bitbucket"
    )
    print_guide_panel(
        "ci",
        content,
        "Generated CI/CD scripts include tests, linters, and security checks.",
    )


@app.command("env")
def guide_env() -> None:
    """Guide for environment management."""
    content = (
        "Manage environment configurations (.env):\n\n"
        "Initialize env files for dev, staging, prod:\n"
        "  devflow env init\n\n"
        "Add key-value environment variables:\n"
        "  devflow env add MY_KEY value --env development\n\n"
        "Switch active .env profile:\n"
        "  devflow env switch production\n\n"
        "Audit keys and check for security vulnerabilities:\n"
        "  devflow env validate"
    )
    print_guide_panel(
        "env",
        content,
        "Add .env* to your .gitignore to prevent leaking configuration secrets.",
    )


@app.command("db")
def guide_db() -> None:
    """Guide for database configuration."""
    content = (
        "Supported databases:\n\n"
        "[bold green]PostgreSQL (recommended for production):[/bold green]\n"
        "  devflow init myproject --db postgresql\n"
        "  DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db\n\n"
        "[bold green]MySQL:[/bold green]\n"
        "  devflow init myproject --db mysql\n"
        "  DATABASE_URL=mysql+aiomysql://user:pass@localhost/db\n\n"
        "[bold green]MongoDB (non-relational):[/bold green]\n"
        "  devflow init myproject --db mongodb\n"
        "  DATABASE_URL=mongodb://localhost:27017/dbname\n"
        "  DATABASE_URL=mongodb+srv://user:pass@cluster.mongodb.net/db\n\n"
        "[bold green]SQLite (local development):[/bold green]\n"
        "  devflow init myproject --db sqlite\n"
        "  DATABASE_URL=sqlite+aiosqlite:///./dbname.db\n\n"
        "Note: MongoDB projects do not support migrations.\n"
        "Note: Switch database by updating DATABASE_URL in .env"
    )
    print_guide_panel(
        "db", content, "Use SQLite for local dev, PostgreSQL for production."
    )


@app.command("config")
def guide_config() -> None:
    """Guide for DevFlow project configuration."""
    content = (
        "Inspect and update DevFlow project settings:\n\n"
        "Show full config:\n"
        "  devflow config show\n\n"
        "Read one setting:\n"
        "  devflow config get db_type\n"
        "  devflow config get api_version\n\n"
        "Update generation settings:\n"
        "  devflow config set db_type postgresql\n"
        "  devflow config set auth_type jwt\n"
        "  devflow config set api_version v2\n"
        "  devflow config set default_tier simple"
    )
    print_guide_panel(
        "config", content, "Config is stored in .devflow.json at the project root."
    )


@app.command("deps")
def guide_deps() -> None:
    """Guide for dependency management."""
    content = (
        "Manage project dependencies with pip integration:\n\n"
        "[bold green]Check installed packages:[/bold green]\n"
        "  devflow deps check\n\n"
        "[bold green]Update all to latest and pin versions:[/bold green]\n"
        "  devflow deps update\n\n"
        "[bold green]Audit for vulnerabilities (exits 1 on HIGH/CRITICAL):[/bold green]\n"
        "  devflow deps audit\n\n"
        "[bold green]Show dependency tree:[/bold green]\n"
        "  devflow deps tree\n\n"
        "[bold green]Add a package and pin in pyproject.toml:[/bold green]\n"
        "  devflow deps add httpx\n"
        "  devflow deps add pytest --dev\n\n"
        "[bold green]Remove a package:[/bold green]\n"
        "  devflow deps remove httpx"
    )
    print_guide_panel(
        "deps", content, "deps audit exits 1 on HIGH/CRITICAL vulnerabilities."
    )


@app.command("cache")
def guide_cache() -> None:
    """Guide for Redis caching."""
    content = (
        "Redis cache management for FastAPI routes:\n\n"
        "[bold green]Initialise cache module:[/bold green]\n"
        "  devflow cache init\n\n"
        "[bold green]Add caching to a GET route:[/bold green]\n"
        "  devflow cache add GET /users --ttl 300\n\n"
        "[bold green]Cache all GET routes at once:[/bold green]\n"
        "  devflow cache add GET / --all-get --ttl 120\n\n"
        "[bold green]Clear cache for a route:[/bold green]\n"
        "  devflow cache clear /users\n\n"
        "[bold green]Clear ALL keys (requires confirmation):[/bold green]\n"
        "  devflow cache clear --all\n\n"
        "[bold green]Check Redis connection status:[/bold green]\n"
        "  devflow cache status\n\n"
        "Notes:\n"
        "  • Only GET routes are cacheable. POST/PUT/DELETE are rejected.\n"
        "  • Auth-guarded routes are namespaced by user ID automatically.\n"
        "  • REDIS_URL is added to all .env* files and settings.py."
    )
    print_guide_panel(
        "cache",
        content,
        "Run devflow event generate startup to register init_cache() on startup.",
    )


@app.command("task")
def guide_task() -> None:
    """Guide for Celery background tasks."""
    content = (
        "Celery background task scaffolding:\n\n"
        "[bold green]Initialise Celery (adds broker/backend to .env):[/bold green]\n"
        "  devflow task init\n\n"
        "[bold green]Generate a task class:[/bold green]\n"
        "  devflow task generate SendEmail\n\n"
        "[bold green]Generate a scheduled task (cron):[/bold green]\n"
        '  devflow task generate DailyReport --schedule "crontab(hour=0, minute=0)"\n\n'
        "[bold green]List all generated tasks:[/bold green]\n"
        "  devflow task list\n\n"
        "[bold green]Run a task immediately:[/bold green]\n"
        "  devflow task run SendEmail\n\n"
        "[bold green]Open Flower monitoring dashboard:[/bold green]\n"
        "  devflow task monitor\n\n"
        "Notes:\n"
        "  • Task arguments are NEVER logged (PII/secrets risk).\n"
        "  • Default retry: max_retries=3, delay=60s, autoretry_for=(Exception,)."
    )
    print_guide_panel(
        "task",
        content,
        "Start Celery worker: celery -A tasks.celery_app worker --loglevel=info",
    )


@app.command("integrate")
def guide_integrate() -> None:
    """Guide for third-party service integrations."""
    content = (
        "Third-party service integration scaffolding:\n\n"
        "[bold green]Email providers:[/bold green]\n"
        "  devflow integrate add --provider email/sendgrid\n"
        "  devflow integrate add --provider email/mailgun\n"
        "  devflow integrate add --provider email/smtp\n\n"
        "[bold green]Payment providers:[/bold green]\n"
        "  devflow integrate add --provider payment/stripe\n"
        "  devflow integrate add --provider payment/paypal\n"
        "  devflow integrate add --provider payment/paymongo\n\n"
        "[bold green]Storage providers:[/bold green]\n"
        "  devflow integrate add --provider storage/s3\n"
        "  devflow integrate add --provider storage/cloudinary\n"
        "  devflow integrate add --provider storage/gcs\n\n"
        "[bold green]Notification providers:[/bold green]\n"
        "  devflow integrate add --provider notify/firebase\n"
        "  devflow integrate add --provider notify/onesignal\n"
        "  devflow integrate add --provider notify/twilio\n\n"
        "[bold green]Monitoring providers:[/bold green]\n"
        "  devflow integrate add --provider monitor/sentry\n"
        "  devflow integrate add --provider monitor/datadog\n\n"
        "[bold green]Search providers:[/bold green]\n"
        "  devflow integrate add --provider search/elasticsearch\n"
        "  devflow integrate add --provider search/meilisearch\n\n"
        "[bold green]List all providers:[/bold green]\n"
        "  devflow integrate list"
    )
    print_guide_panel(
        "integrate",
        content,
        "API keys are always loaded from settings — never hardcoded.",
    )


@app.command("api")
def guide_api() -> None:
    """Guide for API inspection, testing, and client generation."""
    content = (
        "API inspection and testing (requires running dev server):\n\n"
        "[bold green]Export OpenAPI spec:[/bold green]\n"
        "  devflow api export --format json\n"
        "  devflow api export --format yaml\n\n"
        "[bold green]Validate the spec:[/bold green]\n"
        "  devflow api validate\n\n"
        "[bold green]List all routes:[/bold green]\n"
        "  devflow api list\n\n"
        "[bold green]Send a test request:[/bold green]\n"
        "  devflow api test GET /users\n"
        '  devflow api test POST /users --body \'{"username":"alice"}\'\n\n'
        "[bold green]Generate Postman collection:[/bold green]\n"
        "  devflow api postman\n\n"
        "[bold green]Generate typed API client:[/bold green]\n"
        "  devflow api client --lang typescript\n"
        "  devflow api client --lang javascript"
    )
    print_guide_panel("api", content, "Start server first: devflow run")


@app.command("quality")
def guide_quality() -> None:
    """Guide for code quality tools."""
    content = (
        "Code quality checks — lint, typecheck, format, security scan:\n\n"
        "[bold green]Run all checks at once:[/bold green]\n"
        "  devflow quality quality .\n\n"
        "[bold green]Lint with ruff:[/bold green]\n"
        "  devflow quality lint .\n\n"
        "[bold green]Type check with mypy:[/bold green]\n"
        "  devflow quality typecheck .\n\n"
        "[bold green]Format with ruff:[/bold green]\n"
        "  devflow quality format .\n\n"
        "[bold green]Security scan with bandit:[/bold green]\n"
        "  devflow quality scan .\n\n"
        "Notes:\n"
        "  • quality exits 1 on any failure.\n"
        "  • Missing tools are marked ⏭️ Skipped, not failed.\n"
        "  • pip-audit is also included in the combined quality check."
    )
    print_guide_panel(
        "quality", content, "Install all tools: pip install ruff mypy bandit pip-audit"
    )


@app.command("deploy")
def guide_deploy() -> None:
    """Guide for deployment configuration and checklist."""
    content = (
        "Deployment configuration and pre-flight checklist:\n\n"
        "[bold green]Generate platform config:[/bold green]\n"
        "  devflow deploy generate --platform railway\n"
        "  devflow deploy generate --platform render\n"
        "  devflow deploy generate --platform fly\n"
        "  devflow deploy generate --platform vps\n\n"
        "[bold green]View deploy readiness checklist:[/bold green]\n"
        "  devflow deploy checklist\n\n"
        "[bold green]Run checklist and exit 1 on failure:[/bold green]\n"
        "  devflow deploy check\n\n"
        "[bold green]Deploy (blocked if checklist has ❌):[/bold green]\n"
        "  devflow deploy run --platform railway\n\n"
        "Notes:\n"
        "  • Credentials are NEVER written into generated config files.\n"
        "  • deploy run requires typed platform name confirmation.\n"
        "  • deploy run is blocked in production environments."
    )
    print_guide_panel(
        "deploy", content, "Fix all checklist items before running devflow deploy run."
    )


@app.command("flags")
def guide_flags() -> None:
    """Guide for feature flag management."""
    content = (
        "Feature flag management with fail-closed defaults:\n\n"
        "[bold green]Initialise flags module:[/bold green]\n"
        "  devflow flags init\n\n"
        "[bold green]Add a flag:[/bold green]\n"
        "  devflow flags add my_new_feature --default false\n"
        "  devflow flags add dark_mode --default true\n\n"
        "[bold green]Enable / disable a flag:[/bold green]\n"
        "  devflow flags enable my_new_feature\n"
        "  devflow flags disable dark_mode\n\n"
        "[bold green]List all flags:[/bold green]\n"
        "  devflow flags list\n\n"
        "[bold green]Use in your code:[/bold green]\n"
        "  from core.flags import is_enabled\n"
        "  if is_enabled('my_new_feature'):\n"
        "      ...\n\n"
        "Notes:\n"
        "  • Flag names must be snake_case.\n"
        "  • Unknown flags always return False (fail-closed, never fail-open)."
    )
    print_guide_panel(
        "flags",
        content,
        "Flags are stored in core/flags.py — commit them to version control.",
    )


@app.command("health-endpoint")
def guide_health_endpoint() -> None:
    """Guide for the /health monitoring endpoint."""
    content = (
        "Generate a production-safe /health monitoring endpoint:\n\n"
        "[bold green]Generate the /health route:[/bold green]\n"
        "  devflow health-endpoint generate\n\n"
        "[bold green]Register in main.py:[/bold green]\n"
        "  from routers.health_router import router as health_router\n"
        "  app.include_router(health_router)\n\n"
        "[bold green]Test the endpoint:[/bold green]\n"
        "  devflow api test GET /health\n\n"
        "Security guarantees:\n"
        "  • No auth required (monitoring probes are unauthenticated)\n"
        "  • Never leaks DATABASE_URL, connection strings, or stack traces\n"
        "  • Never leaks dependency versions\n"
        "  • Rate-limited at ~300/min (probes won't hit 429s)\n"
        "  • Cache check auto-detected from core/cache.py presence"
    )
    print_guide_panel(
        "health-endpoint",
        content,
        "Run devflow cache init first to include cache status in /health.",
    )


# ===========================================================================
# Phase 5 guide pages
# ===========================================================================


@app.command("cloud")
def guide_cloud() -> None:
    """Guide for cloud database setup (Supabase, MongoDB Atlas, Firebase)."""
    content = (
        "Connect DevFlow to a cloud database provider:\n\n"
        "[bold green]Step 1 — Run the connection wizard:[/bold green]\n"
        "  devflow cloud connect\n"
        "  devflow cloud connect --provider supabase\n"
        "  devflow cloud connect --provider atlas\n"
        "  devflow cloud connect --provider firebase\n\n"
        "[bold green]Supabase (PostgreSQL-compatible):[/bold green]\n"
        "  • Requires: Project URL + Database password\n"
        "  • Stores both pooled (port 6543) and direct (port 5432) URLs\n"
        "  • Direct URL → Alembic migrations  |  Pooled URL → app runtime\n"
        "  • Alembic migrations fully supported (same as local PostgreSQL)\n"
        "  • Env keys: SUPABASE_DB_URL, SUPABASE_DB_URL_DIRECT, DATABASE_URL\n\n"
        "[bold green]MongoDB Atlas:[/bold green]\n"
        "  • Requires: mongodb+srv:// connection string\n"
        "  • Validated by regex before accepting (must start with mongodb+srv://)\n"
        "  • Reuses existing Beanie/Motor templates unchanged\n"
        "  • No migrations (schemaless) — devflow migrate blocked\n"
        "  • Env keys: ATLAS_URI, DATABASE_URL\n\n"
        "[bold green]Firebase Firestore:[/bold green]\n"
        "  • Requires: Path to service-account JSON file\n"
        "  • File is validated (project_id, private_key, client_email required)\n"
        "  • Filename added to .gitignore — NEVER committed to repo\n"
        "  • Uses google-cloud-firestore async client\n"
        "  • New 5-layer template set (model → repository → schema → service → router)\n"
        "  • devflow migrate blocked on Firebase projects\n"
        "  • Env keys: FIREBASE_CREDENTIALS_PATH, FIREBASE_PROJECT_ID\n\n"
        "[bold green]Status & management:[/bold green]\n"
        "  devflow cloud status          Show provider, latency, fallback mode\n"
        "  devflow cloud test            Round-trip health check\n"
        "  devflow cloud disconnect      Revert to local database\n"
        "  devflow db switch supabase    Alias → runs cloud connect wizard"
    )
    print_guide_panel(
        "cloud",
        content,
        "After connecting, run: devflow cloud fallback enable",
    )


@app.command("fallback")
def guide_fallback() -> None:
    """Guide for cloud → local fallback mode."""
    content = (
        "DevFlow generates a resilience layer for cloud outages:\n\n"
        "[bold green]Enable fallback:[/bold green]\n"
        "  devflow cloud fallback enable\n\n"
        "  This generates core/fallback.py into your project with:\n"
        "  • FallbackMode enum: CLOUD / DEGRADED / RECOVERED\n"
        "  • Background health probe (default every 30s)\n"
        "  • Automatic mode transitions on failure / recovery\n\n"
        "[bold green]Modes:[/bold green]\n"
        "  CLOUD      Normal — all reads/writes hit the cloud\n"
        "  DEGRADED   Cloud unreachable → reads served locally, writes queued\n"
        "  RECOVERED  Cloud back → queue replayed, then → CLOUD\n\n"
        "[bold green]DEGRADED behaviour:[/bold green]\n"
        "  Supabase  → reads from local SQLite mirror (.devflow/fallback.db)\n"
        "  Atlas     → local MongoDB if reachable, else JSON cache\n"
        "  Firebase  → JSON snapshot cache (.devflow/fallback/)\n"
        "  Writes    → queued to .devflow/fallback/write_queue.jsonl (202 Accepted)\n"
        "  Header    → X-DevFlow-Mode: degraded on every response\n\n"
        "[bold green]Configuration:[/bold green]\n"
        "  FALLBACK_PROBE_INTERVAL=30   Seconds between health probes\n"
        "  Failures threshold: 3 consecutive failures → DEGRADED\n\n"
        "[bold green]Queue management:[/bold green]\n"
        "  devflow cloud fallback status   Mode + queued write count\n"
        "  devflow cloud fallback sync     Manual replay attempt\n"
        "  devflow cloud fallback disable  Remove fallback wiring\n\n"
        "[bold green]Security:[/bold green]\n"
        "  • Queue/mirror files: 0600 permissions, gitignored\n"
        "  • Status shows counts only — never row contents\n"
        "  • Passwords hashed before queueing (service layer order preserved)\n"
        "  • Conflicts moved to .devflow/fallback/conflicts.jsonl — never silent overwrite\n"
        "  • Generated tests force CLOUD mode with mocked client"
    )
    print_guide_panel(
        "fallback",
        content,
        "Set FALLBACK_PROBE_INTERVAL in .env to tune probe frequency.",
    )


@app.command("menu")
def guide_menu() -> None:
    """Guide for using the interactive command palette."""
    content = (
        "devflow menu opens a fuzzy-searchable palette of all ~175 commands:\n\n"
        "[bold green]Open the palette:[/bold green]\n"
        "  devflow menu\n"
        "  devflow menu mig          (pre-filter to 'mig')\n\n"
        "[bold green]How it works:[/bold green]\n"
        "  1. Start typing to filter commands in real-time (fuzzy match)\n"
        "  2. Use ↑/↓ arrow keys to navigate results\n"
        "  3. Press Enter to select a command\n"
        "  4. DevFlow prints the raw CLI command before running:\n\n"
        '     Running: devflow generate model User --fields "name:str, email:str"\n\n'
        "  This teaches you the full command syntax as you go.\n\n"
        "[bold green]Keyboard shortcuts:[/bold green]\n"
        "  Enter        Run selected command\n"
        "  Ctrl+C       Exit palette cleanly (no traceback)\n"
        "  Type text    Filter commands in real-time\n\n"
        "[bold green]Command categories shown in palette:[/bold green]\n"
        "  Scaffolding · Database · Cloud · Security & Auth\n"
        "  Environment · Docker & CI · Quality · Testing\n"
        "  Deployment · Caching · Background Tasks · API & Profiling\n"
        "  Integrations · Health & Monitoring · Docs & Versioning\n\n"
        "[bold green]Tips:[/bold green]\n"
        "  • Fuzzy search: type 'mig' to find all migrate commands\n"
        "  • Type 'cloud' to find all cloud provider commands\n"
        "  • Type 'guide' to find all tutorial guides"
    )
    print_guide_panel(
        "menu",
        content,
        "Run devflow menu to open the palette right now!",
    )


@app.command("sync")
def guide_sync() -> None:
    """Guide for cascading model field changes across all layers."""
    content = (
        "devflow sync model closes the field-refresh gap: after you add or remove a\n"
        "field, it regenerates the mechanical layers so they stay in step.\n\n"
        "[bold green]Add a field inline and cascade it:[/bold green]\n"
        '  devflow sync model User --fields "phone:str, verified:bool"\n\n'
        "[bold green]Already edited the model file by hand? Just sync:[/bold green]\n"
        "  devflow sync model User        (reads new fields back from models/user.py)\n\n"
        "[bold green]Preview without writing anything:[/bold green]\n"
        "  devflow sync model User --dry-run\n\n"
        "[bold green]Sync every registered model:[/bold green]\n"
        "  devflow sync model --all\n\n"
        "[bold green]What each layer does:[/bold green]\n"
        "  Model       apply field changes        (overwrite with confirm)\n"
        "  Schema      regenerate (mirrors fields) (confirm per file)\n"
        "  Router      regenerate (schema refs)    (confirm per file)\n"
        "  Repository  untouched                   (skipped)\n"
        "  Service     flagged for manual review   (never auto-rewritten)\n\n"
        "[bold green]Notes:[/bold green]\n"
        "  • Removed fields require a typed confirmation — never silently dropped.\n"
        '  • After a relational sync, run: devflow migrate make "sync user"\n'
        "  • The field snapshot in .devflow.json is updated so the next diff is accurate."
    )
    print_guide_panel(
        "sync",
        content,
        "Use --dry-run first to preview the per-layer plan.",
    )
