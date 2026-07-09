"""DevFlow deps command group — dependency management with Rich-wrapped pip output."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from devflow.console import console

app = typer.Typer(help="Dependency management — check, update, audit, tree, add, remove.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pip(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run pip with the current Python executable.

    Args:
        *args: Arguments to pass to pip.
        capture: Whether to capture stdout/stderr.

    Returns:
        CompletedProcess result.
    """
    cmd = [sys.executable, "-m", "pip", *args]
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
    )


def _read_pyproject_deps() -> list[str]:
    """Read dependencies from pyproject.toml if present.

    Returns:
        List of dependency strings.
    """
    pp = Path.cwd() / "pyproject.toml"
    if not pp.exists():
        return []
    try:
        content = pp.read_text(encoding="utf-8")
        m = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if m:
            raw = m.group(1)
            return [line.strip().strip('",').strip() for line in raw.splitlines() if line.strip().strip('",')]
    except Exception:
        pass
    return []


def _pin_version(package: str) -> Optional[str]:
    """Get the currently installed version of a package.

    Args:
        package: Package name to look up.

    Returns:
        Version string, or None if not found.
    """
    result = _pip("show", package)
    for line in result.stdout.splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("check")
def deps_check() -> None:
    """Check installed packages against pyproject.toml requirements."""
    deps = _read_pyproject_deps()
    if not deps:
        console.print("[yellow]No dependencies found in pyproject.toml[/yellow]")
        return

    table = Table(title="Dependency Check", border_style="cyan")
    table.add_column("Package", style="bold")
    table.add_column("Required")
    table.add_column("Installed")
    table.add_column("Status")

    for dep in deps:
        pkg_name = re.split(r"[><=!]", dep)[0].strip()
        result = _pip("show", pkg_name)
        installed_ver = None
        for line in result.stdout.splitlines():
            if line.startswith("Version:"):
                installed_ver = line.split(":", 1)[1].strip()
                break
        status = "[green]✅ OK[/green]" if installed_ver else "[red]❌ Missing[/red]"
        table.add_row(pkg_name, dep, installed_ver or "[dim]not installed[/dim]", status)

    console.print(table)


@app.command("update")
def deps_update() -> None:
    """Update all dependencies to latest compatible versions and pin exact versions in pyproject.toml."""
    deps = _read_pyproject_deps()
    if not deps:
        console.print("[yellow]No dependencies found in pyproject.toml[/yellow]")
        return

    console.print("[cyan]Updating dependencies...[/cyan]\n")

    pp = Path.cwd() / "pyproject.toml"
    content = pp.read_text(encoding="utf-8") if pp.exists() else ""

    updated: list[tuple[str, str, str]] = []

    table = Table(title="Dependency Update", border_style="cyan")
    table.add_column("Package", style="bold")
    table.add_column("Old Version")
    table.add_column("New Version")
    table.add_column("Status")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Updating packages...", total=len(deps))
        for dep in deps:
            pkg_name = re.split(r"[><!=]", dep)[0].strip()
            old_ver = _pin_version(pkg_name) or "unknown"

            progress.update(task, description=f"[cyan]  Updating {pkg_name}...")
            result = _pip("install", "--upgrade", pkg_name, capture=True)

            new_ver = _pin_version(pkg_name) or old_ver
            status = "[green]✅ Updated[/green]" if result.returncode == 0 else "[red]❌ Failed[/red]"
            table.add_row(pkg_name, old_ver, new_ver, status)

            if result.returncode == 0 and new_ver != old_ver:
                updated.append((pkg_name, old_ver, new_ver))
                # Pin exact version in pyproject.toml
                if content:
                    content = re.sub(
                        rf'"{re.escape(dep)}"',
                        f'"{pkg_name}=={new_ver}"',
                        content,
                    )
            progress.advance(task)

    console.print(table)

    if updated and pp.exists() and content:
        pp.write_text(content, encoding="utf-8")
        console.print(
            Panel(
                f"[green]✅ Pinned {len(updated)} package(s) in pyproject.toml[/green]",
                border_style="green",
            )
        )


@app.command("audit")
def deps_audit() -> None:
    """Audit dependencies for known vulnerabilities using pip-audit.

    Exits with code 1 if HIGH or CRITICAL vulnerabilities are found.
    """
    if not shutil.which("pip-audit") and not _try_pip_audit_module():
        console.print(
            Panel(
                "[yellow]pip-audit not found.\nInstall with: pip install pip-audit[/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    console.print("[cyan]Running dependency audit...[/cyan]")
    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--format", "json"],
        capture_output=True,
        text=True,
    )

    try:
        import json
        data = json.loads(result.stdout)
        vulns = data.get("vulnerabilities", []) if isinstance(data, dict) else []
    except Exception:
        # Fallback: print raw output
        console.print(result.stdout or result.stderr)
        if result.returncode != 0:
            raise typer.Exit(1)
        return

    if not vulns:
        console.print(Panel("[green]✅ No known vulnerabilities found.[/green]", border_style="green"))
        return

    table = Table(title="Vulnerability Report", border_style="red")
    table.add_column("Package", style="bold")
    table.add_column("Version")
    table.add_column("ID")
    table.add_column("Severity")
    table.add_column("Fix Available")

    has_critical = False
    for v in vulns:
        pkg = v.get("name", "unknown")
        ver = v.get("version", "unknown")
        for vuln in v.get("vulns", []):
            vid = vuln.get("id", "unknown")
            severity = vuln.get("fix_versions", [])
            fix = ", ".join(severity) if severity else "None"
            sev_label = vuln.get("aliases", [vid])[0] if vuln.get("aliases") else vid
            if any(word in sev_label.upper() for word in ("HIGH", "CRITICAL", "CVE")):
                has_critical = True
            table.add_row(pkg, ver, vid, sev_label, fix)

    console.print(table)

    if has_critical:
        console.print(Panel("[red]❌ HIGH/CRITICAL vulnerabilities found. Fix immediately.[/red]", border_style="red"))
        raise typer.Exit(1)


def _try_pip_audit_module() -> bool:
    """Check if pip_audit is importable as a module.

    Returns:
        True if pip_audit module is available.
    """
    try:
        import pip_audit  # noqa: F401
        return True
    except ImportError:
        return False


@app.command("tree")
def deps_tree() -> None:
    """Display the dependency tree using pipdeptree or pip show."""
    if shutil.which("pipdeptree"):
        subprocess.run(["pipdeptree"])
        return

    # Fallback: show installed packages
    result = _pip("list", "--format", "columns")
    console.print(
        Panel(
            result.stdout,
            title="Installed Packages",
            border_style="cyan",
        )
    )
    console.print(
        "[dim]Tip: Install pipdeptree for a full dependency tree: pip install pipdeptree[/dim]"
    )


@app.command("add")
def deps_add(
    package: Annotated[str, typer.Argument(help="Package to install (e.g. httpx or httpx==0.27.0)")],
    dev: Annotated[bool, typer.Option("--dev", help="Add as a dev dependency")] = False,
) -> None:
    """Install a package and add it to pyproject.toml.

    Args:
        package: Package name or pinned spec (e.g. 'httpx' or 'httpx>=0.27.0').
        dev: If True, add to [project.optional-dependencies].dev instead.
    """
    from devflow.commands.project import install_packages

    console.print(f"[cyan]Installing {package}...[/cyan]")
    installed, failed, skipped = install_packages([package])

    if failed:
        raise typer.Exit(1)

    # Pin version in pyproject.toml
    pp = Path.cwd() / "pyproject.toml"
    if not pp.exists():
        console.print("[dim]No pyproject.toml found — skipping pin.[/dim]")
        return

    version = _pin_version(package.split(">=")[0].split("==")[0])
    pin = f"{package.split('>=')[0].split('==')[0]}=={version}" if version else package
    content = pp.read_text(encoding="utf-8")

    if dev:
        # Add to [project.optional-dependencies].dev
        content = re.sub(
            r'(dev\s*=\s*\[)',
            rf'\1\n    "{pin}",',
            content,
        )
    else:
        # Add to [project.dependencies]
        content = re.sub(
            r'(dependencies\s*=\s*\[)',
            rf'\1\n    "{pin}",',
            content,
        )

    pp.write_text(content, encoding="utf-8")
    console.print(
        Panel(
            f"[green]✅ {pin} installed and pinned in pyproject.toml[/green]",
            border_style="green",
        )
    )


@app.command("remove")
def deps_remove(
    package: Annotated[str, typer.Argument(help="Package to uninstall")],
) -> None:
    """Uninstall a package and remove it from pyproject.toml.

    Args:
        package: Package name to remove.
    """
    result = _pip("uninstall", package, "-y", capture=True)
    if result.returncode != 0:
        console.print(f"[red]Failed to uninstall {package}: {result.stderr.strip()}[/red]")
        raise typer.Exit(1)

    # Remove from pyproject.toml
    pp = Path.cwd() / "pyproject.toml"
    if pp.exists():
        content = pp.read_text(encoding="utf-8")
        # Remove any line containing the package name in dependencies
        lines = content.splitlines(keepends=True)
        new_lines = [
            line for line in lines
            if not re.search(rf'"{re.escape(package)}[><=!@"]*"', line)
        ]
        pp.write_text("".join(new_lines), encoding="utf-8")

    console.print(
        Panel(
            f"[green]✅ {package} removed and unpinned from pyproject.toml[/green]",
            border_style="green",
        )
    )
