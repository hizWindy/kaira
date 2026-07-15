"""Project health check command."""

from __future__ import annotations

from pathlib import Path

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
    routers_count = (
        len(list(routers_dir.glob("*_router.py"))) if routers_dir.exists() else 0
    )
    routers_ok = routers_count > 0

    # 3. Tests
    tests_dir = output_root / "tests"
    test_files_count = (
        len(list(tests_dir.glob("test_*_router.py"))) if tests_dir.exists() else 0
    )
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
    items: list[tuple[str, str, str]] = []

    # 1. Models
    if models_ok:
        items.append(
            (
                "Models",
                "[bold green]✅ HEALTHY[/bold green]",
                f"{models_count} detected",
            )
        )
    else:
        items.append(("Models", "[bold red]❌ MISSING[/bold red]", "No models found"))
        overall_score -= 15

    # 2. Routers
    if routers_ok:
        items.append(
            (
                "Routers",
                "[bold green]✅ HEALTHY[/bold green]",
                f"{routers_count} registered",
            )
        )
    else:
        items.append(("Routers", "[bold red]❌ MISSING[/bold red]", "No routers found"))
        overall_score -= 15

    # 3. Tests
    if tests_ok:
        items.append(
            ("Tests", "[bold green]✅ HEALTHY[/bold green]", "All models have tests")
        )
    elif tests_partial:
        items.append(
            (
                "Tests",
                "[bold yellow]⚠️  WARNING[/bold yellow]",
                f"{test_files_count}/{routers_count} models have tests",
            )
        )
        overall_score -= 10
    else:
        items.append(
            ("Tests", "[bold red]❌ MISSING[/bold red]", "No test suites generated")
        )
        overall_score -= 20

    # 4. Auth
    if auth_ok:
        items.append(
            (
                "Auth",
                "[bold green]✅ SECURE[/bold green]",
                "Boilerplate and guards active",
            )
        )
    else:
        items.append(
            ("Auth", "[bold red]❌ INSECURE[/bold red]", "No auth guard detected")
        )
        security_score -= 30
        overall_score -= 15

    # 6. Migrations
    if migrations_ok:
        items.append(
            ("Migrations", "[bold green]✅ HEALTHY[/bold green]", "Up to date")
        )
    else:
        items.append(
            ("Migrations", "[bold red]❌ MISSING[/bold red]", "Not initialized")
        )
        overall_score -= 10

    # 6. Docker
    if docker_ok:
        items.append(
            ("Docker", "[bold green]✅ ACTIVE[/bold green]", "Dockerfile configured")
        )
    else:
        items.append(
            ("Docker", "[bold yellow]⚠️  WARNING[/bold yellow]", "No Dockerfile found")
        )
        overall_score -= 5

    # 7. Rate Limiting
    if rate_limit_ok:
        items.append(
            ("Rate Limiting", "[bold green]✅ SECURE[/bold green]", "Configured")
        )
    else:
        items.append(
            ("Rate Limiting", "[bold red]❌ INSECURE[/bold red]", "Not configured")
        )
        security_score -= 20
        overall_score -= 10

    # 8. Environment
    if env_ok:
        items.append(
            (
                "Environment",
                "[bold green]✅ HEALTHY[/bold green]",
                "Active environment present (.env)",
            )
        )
    else:
        items.append(
            (
                "Environment",
                "[bold red]❌ MISSING[/bold red]",
                "Missing active env config (.env)",
            )
        )
        security_score -= 10
        overall_score -= 10

    # 9. CI/CD
    if ci_ok:
        items.append(("CI/CD", "[bold green]✅ ACTIVE[/bold green]", "Pipeline active"))
    else:
        items.append(
            ("CI/CD", "[bold yellow]⚠️  WARNING[/bold yellow]", "No pipeline detected")
        )
        overall_score -= 5

    security_score = max(0, security_score)
    overall_score = max(0, overall_score)

    # Print a beautiful Table with SIMPLE_HEAD box style
    from rich import box
    from devflow.core.theme import Theme
    from rich.table import Table

    table = Table(box=box.SIMPLE_HEAD, border_style=Theme.PRIMARY, show_header=True)
    table.add_column("Aspect", style=f"bold {Theme.PRIMARY}", width=18)
    table.add_column("Status", width=16)
    table.add_column("Details", style=Theme.MUTED)

    for aspect, status, details in items:
        table.add_row(aspect, status, details)

    console.print(table)
    console.print()

    # Print score panels side-by-side
    from rich.columns import Columns
    from rich.align import Align

    sec_color = (
        "green"
        if security_score >= 80
        else ("yellow" if security_score >= 60 else "red")
    )
    ovr_color = (
        "green" if overall_score >= 80 else ("yellow" if overall_score >= 60 else "red")
    )

    sec_panel = Panel(
        Align.center(
            f"[bold {sec_color}]{security_score}[/][dim]/100[/dim]"
        ),
        title="[bold]Security Score[/bold]",
        border_style=sec_color,
        width=24,
    )

    ovr_panel = Panel(
        Align.center(
            f"[bold {ovr_color}]{overall_score}[/][dim]/100[/dim]"
        ),
        title="[bold]Overall Health[/bold]",
        border_style=ovr_color,
        width=24,
    )

    console.print(Columns([sec_panel, ovr_panel], expand=False))
    console.print()

    # Suggestions
    suggestions = []
    if not auth_ok:
        suggestions.append(
            "Run [bold cyan]devflow auth generate --type jwt[/bold cyan] to generate authentication logic"
        )
    if not rate_limit_ok:
        suggestions.append(
            "Run [bold cyan]devflow auth generate[/bold cyan] to add rate limiting support"
        )
    if not docker_ok:
        suggestions.append(
            "Run [bold cyan]devflow docker init --with-compose[/bold cyan] to dockerise project"
        )
    if not ci_ok:
        suggestions.append(
            "Run [bold cyan]devflow ci generate --platform github[/bold cyan] to configure pipeline"
        )
    if not tests_ok:
        suggestions.append(
            "Run [bold cyan]devflow test generate --all[/bold cyan] to generate testing suite"
        )

    if suggestions:
        sug_lines = "\n".join(
            f"[bold yellow]→[/bold yellow] {sug}" for sug in suggestions
        )
        console.print(
            Panel(
                sug_lines,
                title="[bold yellow]Recommended Actions[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]✔ Your project is in perfect health![/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
