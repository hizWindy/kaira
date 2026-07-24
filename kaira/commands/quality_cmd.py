"""Kaira quality command group — lint, typecheck, format, scan, and combined quality check."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

app = typer.Typer(help="Code quality tools — lint, typecheck, format, scan, audit.")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TOOL_INSTALL_HINTS: dict[str, str] = {
    "ruff": "pip install ruff",
    "mypy": "pip install mypy",
    "bandit": "pip install bandit",
    "pip-audit": "pip install pip-audit",
}


def _run_tool(
    name: str,
    cmd: list[str],
    *,
    label: str,
    table: Table,
    check_exit: bool = True,
) -> bool:
    """Run an external quality tool and record the result in *table*.

    Args:
        name: Tool binary name (used for PATH lookup and install hint).
        cmd: Full command list to execute.
        label: Display label shown in the results table.
        table: Rich Table to append the result row to.
        check_exit: If True, count non-zero exit as a failure.

    Returns:
        True if the tool passed, False on failure or skip.
    """
    if not shutil.which(name):
        table.add_row(label, "⏭️ Skipped", f"[dim]Install: {_TOOL_INSTALL_HINTS.get(name, name)}[/dim]")
        return True  # Skipped ≠ failure; don't exit 1 for missing tool

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        passed = result.returncode == 0 or not check_exit
        status = "[green]✅ Passed[/green]" if passed else "[red]❌ Failed[/red]"
        detail = ""
        if not passed and result.stdout.strip():
            # Show first 3 lines of output
            lines = result.stdout.strip().splitlines()[:3]
            detail = "\n".join(lines)
        table.add_row(label, status, detail or "[dim]—[/dim]")
        return passed
    except Exception as exc:
        table.add_row(label, "[red]❌ Error[/red]", str(exc))
        return False


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("lint")
def quality_lint(
    path: Annotated[str, typer.Argument(help="Path to lint (default: kaira/ or .)")] = ".",
) -> None:
    """Run ruff check on the project.

    Args:
        path: Directory or file to lint.
    """
    if not shutil.which("ruff"):
        console.print("[yellow]ruff not found. Install with: pip install ruff[/yellow]")
        raise typer.Exit(1)
    result = subprocess.run(["ruff", "check", path], text=True, capture_output=False)
    if result.returncode != 0:
        raise typer.Exit(1)


@app.command("typecheck")
def quality_typecheck(
    path: Annotated[str, typer.Argument(help="Path to typecheck (default: .)")] = ".",
) -> None:
    """Run mypy type checking on the project.

    Args:
        path: Directory or file to typecheck.
    """
    if not shutil.which("mypy"):
        console.print("[yellow]mypy not found. Install with: pip install mypy[/yellow]")
        raise typer.Exit(1)
    result = subprocess.run(["mypy", path, "--ignore-missing-imports"], capture_output=False)
    if result.returncode != 0:
        raise typer.Exit(1)


@app.command("format")
def quality_format(
    path: Annotated[str, typer.Argument(help="Path to format (default: .)")] = ".",
) -> None:
    """Run ruff format on the project.

    Args:
        path: Directory or file to format.
    """
    if not shutil.which("ruff"):
        console.print("[yellow]ruff not found. Install with: pip install ruff[/yellow]")
        raise typer.Exit(1)
    subprocess.run(["ruff", "check", "--fix", path])
    subprocess.run(["ruff", "format", path])


@app.command("scan")
def quality_scan(
    path: Annotated[str, typer.Argument(help="Path to scan (default: .)")] = ".",
) -> None:
    """Run bandit security scan on the project.

    Args:
        path: Directory or file to scan.
    """
    if not shutil.which("bandit"):
        console.print("[yellow]bandit not found. Install with: pip install bandit[/yellow]")
        raise typer.Exit(1)
    result = subprocess.run(["bandit", "-ll", "-r", path], capture_output=False)
    if result.returncode != 0:
        raise typer.Exit(1)


@app.command("quality")
def quality_all(
    path: Annotated[str, typer.Argument(help="Path to check (default: .)")] = ".",
) -> None:
    """Run all quality checks: lint, typecheck, format, scan, and pip-audit.

    Exits with code 1 if any check fails. Missing tools are marked Skipped, not failed.

    Args:
        path: Directory to check.
    """
    console.print("[cyan]⚡ Kaira Quality Check[/cyan]\n")

    table = Table(title="Quality Results", border_style="cyan")
    table.add_column("Tool", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    failures = 0

    checks = [
        ("ruff", ["ruff", "check", path], "Lint (ruff)"),
        ("ruff", ["ruff", "format", "--check", path], "Format (ruff)"),
        ("mypy", ["mypy", path, "--ignore-missing-imports"], "Type Check (mypy)"),
        ("bandit", ["bandit", "-ll", "-r", path], "Security Scan (bandit)"),
        ("pip-audit", ["pip-audit"], "Vulnerability Audit (pip-audit)"),
    ]

    for tool_name, cmd, label in checks:
        passed = _run_tool(tool_name, cmd, label=label, table=table)
        if not passed:
            failures += 1

    console.print(table)

    if failures == 0:
        console.print(Panel("[green]✅ All quality checks passed![/green]", border_style="green"))
    else:
        console.print(
            Panel(
                f"[red]❌ {failures} check(s) failed. Fix the issues above and re-run.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)
