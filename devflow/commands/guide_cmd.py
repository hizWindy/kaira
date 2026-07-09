"""Guide command module containing beautiful, copy-pasteable CLI tutorials and tips."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from devflow.console import console

app = typer.Typer(help="Interactive guides for all DevFlow operations.")

def print_guide_panel(title: str, content: str, tip: str) -> None:
    """Helper to display guide content with standard Rich layout."""
    full_text = f"{content.strip()}\n"
    if tip:
        full_text += f"\n[bold cyan]Tip:[/bold cyan] {tip}"
    
    console.print(Panel(
        full_text,
        title=f"⚡ DevFlow — Guide: {title}",
        border_style="cyan",
        expand=False,
    ))

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
            "  [bold cyan]devflow guide health-endpoint[/bold cyan]   Health monitoring endpoint"
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
    print_guide_panel("init", content, "Run devflow init without flags for interactive wizard.")

@app.command("generate")
def guide_generate() -> None:
    """Guide for model & layer generation."""
    content = (
        "Generate all 5 layers for a model:\n"
        "  devflow generate model User \\\n"
        "    --fields \"username:str, email:str, age:int\"\n\n"
        "Generate with tier:\n"
        "  devflow generate model User \\\n"
        "    --fields \"username:str, email:str\" \\\n"
        "    --tier simple\n\n"
        "  devflow generate model User \\\n"
        "    --fields \"username:str, email:str\" \\\n"
        "    --tier full\n\n"
        "Add relationships after generation:\n"
        "  devflow add relation Post --has-one User\n"
        "  devflow add relation Post --has-many Comment --cascade \"all, delete-orphan\"\n"
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
        "      \"name\": \"User\",\n"
        "      \"fields\": {\n"
        "        \"username\": \"str\",\n"
        "        \"email\": \"str\",\n"
        "        \"age\": \"int\"\n"
        "      }\n"
        "    },\n"
        "    {\n"
        "      \"name\": \"Post\",\n"
        "      \"fields\": {\n"
        "        \"title\": \"str\",\n"
        "        \"body\": \"str\"\n"
        "      },\n"
        "      \"relations\": [\n"
        "        {\n"
        "          \"type\": \"many-to-one\",\n"
        "          \"target\": \"User\"\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]"
    )
    print_guide_panel("generate", content, "Model names must be PascalCase. Fields are snake_case.")

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
    print_guide_panel("auth", content, "Always run devflow audit security after adding guards.")

@app.command("migrate")
def guide_migrate() -> None:
    """Guide for database migrations."""
    content = (
        "Database migration operations (relational databases only):\n\n"
        "Initialize Alembic:\n"
        "  devflow migrate init\n\n"
        "Create migration revision:\n"
        "  devflow migrate make \"add users table\"\n\n"
        "Run pending migrations:\n"
        "  devflow migrate run\n\n"
        "Rollback last migration:\n"
        "  devflow migrate rollback"
    )
    print_guide_panel("migrate", content, "MongoDB does not use migrations or support migration commands.")

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
    print_guide_panel("security", content, "Security is applied by default starting from project initialization.")

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
    print_guide_panel("docker", content, "Docker run uses security-hardened flags by default.")

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
    print_guide_panel("ci", content, "Generated CI/CD scripts include tests, linters, and security checks.")

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
    print_guide_panel("env", content, "Add .env* to your .gitignore to prevent leaking configuration secrets.")

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
    print_guide_panel("db", content, "Use SQLite for local dev, PostgreSQL for production.")


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
    print_guide_panel("config", content, "Config is stored in .devflow.json at the project root.")


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
    print_guide_panel("deps", content, "deps audit exits 1 on HIGH/CRITICAL vulnerabilities.")


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
    print_guide_panel("cache", content, "Run devflow event generate startup to register init_cache() on startup.")


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
    print_guide_panel("task", content, "Start Celery worker: celery -A tasks.celery_app worker --loglevel=info")


@app.command("integrate")
def guide_integrate() -> None:
    """Guide for third-party service integrations."""
    content = (
        "Third-party service integration scaffolding:\n\n"
        "[bold green]Email providers:[/bold green]\n"
        "  devflow integrate --provider email/sendgrid\n"
        "  devflow integrate --provider email/mailgun\n"
        "  devflow integrate --provider email/smtp\n\n"
        "[bold green]Payment providers:[/bold green]\n"
        "  devflow integrate --provider payment/stripe\n"
        "  devflow integrate --provider payment/paypal\n"
        "  devflow integrate --provider payment/paymongo\n\n"
        "[bold green]Storage providers:[/bold green]\n"
        "  devflow integrate --provider storage/s3\n"
        "  devflow integrate --provider storage/cloudinary\n"
        "  devflow integrate --provider storage/gcs\n\n"
        "[bold green]Notification providers:[/bold green]\n"
        "  devflow integrate --provider notify/firebase\n"
        "  devflow integrate --provider notify/onesignal\n"
        "  devflow integrate --provider notify/twilio\n\n"
        "[bold green]Monitoring providers:[/bold green]\n"
        "  devflow integrate --provider monitor/sentry\n"
        "  devflow integrate --provider monitor/datadog\n\n"
        "[bold green]Search providers:[/bold green]\n"
        "  devflow integrate --provider search/elasticsearch\n"
        "  devflow integrate --provider search/meilisearch\n\n"
        "[bold green]List all providers:[/bold green]\n"
        "  devflow integrate list"
    )
    print_guide_panel("integrate", content, "API keys are always loaded from settings — never hardcoded.")


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
    print_guide_panel("api", content, "Start server first: uvicorn main:app --reload")


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
    print_guide_panel("quality", content, "Install all tools: pip install ruff mypy bandit pip-audit")


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
    print_guide_panel("deploy", content, "Fix all checklist items before running devflow deploy run.")


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
    print_guide_panel("flags", content, "Flags are stored in core/flags.py — commit them to version control.")


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

