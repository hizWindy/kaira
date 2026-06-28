"""Project health check command."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import typer
from rich.panel import Panel

from devflow.config import get_config
from devflow.console import console

app = typer.Typer(help="Project Health Check command.")


@app.command("run")
def health_command() -> None:
    """Run a comprehensive health audit of the DevFlow project."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    console.print("[cyan]⚡ Running DevFlow Health Check...[/cyan]\n")

    # 1. Models
    models_dir = output_root / config.models_dir
    models_count = len(list(models_dir.glob("*.py"))) if models_dir.exists() else 0
    models_ok = models_count > 0

    # 2. Routers
    routers_dir = output_root / config.routers_dir
    routers_count = len(list(routers_dir.glob("*_router.py"))) if routers_dir.exists() else 0
    routers_ok = routers_count > 0

    # 3. Tests
    tests_dir = output_root / "tests"
    test_files_count = len(list(tests_dir.glob("test_*_router.py"))) if tests_dir.exists() else 0
    tests_ok = routers_count > 0 and test_files_count >= routers_count
    tests_partial = routers_count > 0 and 0 < test_files_count < routers_count

    # 4. Auth
    auth_dir = output_root / "auth"
    auth_ok = auth_dir.exists() and (auth_dir / "dependencies.py").exists()

    # 5. Migrations
    alembic_dir = output_root / "alembic"
    migrations_ok = alembic_dir.exists()

    # 6. Docker
    dockerfile = output_root / "Dockerfile"
    docker_ok = dockerfile.exists()

    # 7. Rate Limiting
    rate_limit_py = output_root / "rate_limit.py"
    rate_limit_ok = rate_limit_py.exists()

    # 8. Environment
    env_file = output_root / ".env"
    env_ok = env_file.exists()

    # 9. CI/CD
    github_ci = output_root / ".github" / "workflows" / "test.yml"
    gitlab_ci = output_root / ".gitlab-ci.yml"
    bitbucket_ci = output_root / "bitbucket-pipelines.yml"
    ci_ok = github_ci.exists() or gitlab_ci.exists() or bitbucket_ci.exists()

    # Count issues to calculate scores
    security_score = 100
    overall_score = 100

    # Calculate scores & statuses
    status_models = "✅ Models:          {} detected".format(models_count)
    if not models_ok:
        status_models = "❌ Models:          No models found"
        overall_score -= 15

    status_routers = "✅ Routers:         {} registered".format(routers_count)
    if not routers_ok:
        status_routers = "❌ Routers:         No routers found"
        overall_score -= 15

    if tests_ok:
        status_tests = "✅ Tests:          All models have tests"
    elif tests_partial:
        status_tests = "⚠️  Tests:          {}/{} models have tests".format(test_files_count, routers_count)
        overall_score -= 10
    else:
        status_tests = "❌ Tests:          No test suites generated"
        overall_score -= 20

    if auth_ok:
        status_auth = "✅ Auth:            Boilerplate and guards active"
    else:
        status_auth = "❌ Auth:            No auth guard detected"
        security_score -= 30
        overall_score -= 15

    if migrations_ok:
        status_migrations = "✅ Migrations:      Up to date"
    else:
        status_migrations = "❌ Migrations:      Not initialized"
        overall_score -= 10

    if docker_ok:
        status_docker = "✅ Docker:         Dockerfile configured"
    else:
        status_docker = "⚠️  Docker:         No Dockerfile found"
        overall_score -= 5

    if rate_limit_ok:
        status_rate = "✅ Rate Limiting:   Configured"
    else:
        status_rate = "❌ Rate Limiting:   Not configured"
        security_score -= 20
        overall_score -= 10

    if env_ok:
        status_env = "✅ Environment:     Active environment present (.env)"
    else:
        status_env = "❌ Environment:     Missing active env config (.env)"
        security_score -= 10
        overall_score -= 10

    if ci_ok:
        status_ci = "✅ CI/CD:          Pipeline active"
    else:
        status_ci = "⚠️  CI/CD:          No pipeline detected"
        overall_score -= 5

    security_score = max(0, security_score)
    overall_score = max(0, overall_score)

    # Print checklist
    checklist = [
        status_models,
        status_routers,
        status_tests,
        status_auth,
        status_migrations,
        status_docker,
        status_rate,
        status_env,
        status_ci
    ]

    console.print("──────────────────────────────────────────")
    for line in checklist:
        console.print(line)
    console.print("──────────────────────────────────────────")

    sec_color = "green" if security_score >= 80 else ("yellow" if security_score >= 60 else "red")
    ovr_color = "green" if overall_score >= 80 else ("yellow" if overall_score >= 60 else "red")

    console.print(f"Security Score:  [{sec_color}]{security_score}/100[/{sec_color}]")
    console.print(f"Overall Score:   [{ovr_color}]{overall_score}/100[/{ovr_color}]\n")

    # Suggestions
    suggestions = []
    if not auth_ok:
        suggestions.append("→ Run [bold]devflow auth generate --type jwt[/bold]")
    if not rate_limit_ok:
        suggestions.append("→ Run [bold]devflow auth generate[/bold] to generate rate limiting code")
    if not docker_ok:
        suggestions.append("→ Run [bold]devflow docker init --with-compose[/bold]")
    if not ci_ok:
        suggestions.append("→ Run [bold]devflow ci generate --platform github[/bold]")
    if not tests_ok:
         suggestions.append("→ Run [bold]devflow test generate --all[/bold]")

    if suggestions:
        console.print("[bold]Suggestions:[/bold]")
        for sug in suggestions:
            console.print(sug)
    else:
        console.print("[green]✔ Your project is in perfect health![/green]")
