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
            "  [bold cyan]devflow guide init[/bold cyan]        Project initialization\n"
            "  [bold cyan]devflow guide generate[/bold cyan]    Model & layer generation\n"
            "  [bold cyan]devflow guide auth[/bold cyan]        Authentication setup\n"
            "  [bold cyan]devflow guide migrate[/bold cyan]     Database migrations\n"
            "  [bold cyan]devflow guide security[/bold cyan]    Security commands\n"
            "  [bold cyan]devflow guide test[/bold cyan]        Test generation & running\n"
            "  [bold cyan]devflow guide docker[/bold cyan]      Docker setup\n"
            "  [bold cyan]devflow guide ci[/bold cyan]          CI/CD pipeline setup\n"
            "  [bold cyan]devflow guide env[/bold cyan]         Environment management\n"
            "  [bold cyan]devflow guide db[/bold cyan]          Database configuration\n"
            "  [bold cyan]devflow guide config[/bold cyan]      DevFlow configuration"
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
