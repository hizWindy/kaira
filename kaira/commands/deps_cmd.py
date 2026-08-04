"""Kaira deps command group — dependency management with Rich-wrapped pip output."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

app = typer.Typer(
    help="Dependency management — check, update, audit, tree, add, remove."
)

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
    from kaira.config import get_venv_python

    python_exe = get_venv_python()
    cmd = [python_exe, "-m", "pip", *args]
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
    )


def _parse_dependency_array(content: str, key: str = "dependencies") -> list[str]:
    """Extract the quoted specs from a TOML array, tracking bracket depth.

    Matching the array with a non-greedy ``\\[(.*?)\\]`` stops at the first
    ``]`` in the file, which is the extras marker inside a spec such as
    ``fastapi[standard]>=0.115.0`` — that truncates the list and mangles the
    entry it stops on.

    Args:
        content: Full ``pyproject.toml`` text.
        key: Array key to read.

    Returns:
        Dependency specs in file order, without duplicates.
    """
    opening = re.search(rf"^\s*{re.escape(key)}\s*=\s*\[", content, re.MULTILINE)
    if not opening:
        return []

    start = opening.end() - 1
    depth = 0
    body = ""
    for index in range(start, len(content)):
        if content[index] == "[":
            depth += 1
        elif content[index] == "]":
            depth -= 1
            if depth == 0:
                body = content[start + 1 : index]
                break
    if not body:
        return []

    body = re.sub(r"#[^\n]*", "", body)  # drop comments
    specs: list[str] = []
    for match in re.finditer(r"[\"']([^\"']+)[\"']", body):
        spec = match.group(1).strip()
        if spec and spec not in specs:
            specs.append(spec)
    return specs


def _read_pyproject_deps() -> list[str]:
    """Read dependencies from pyproject.toml if present.

    Returns:
        List of dependency strings.
    """
    pp = Path.cwd() / "pyproject.toml"
    if not pp.exists():
        return []
    try:
        return _parse_dependency_array(pp.read_text(encoding="utf-8"))
    except OSError:
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
        table.add_row(
            pkg_name, dep, installed_ver or "[dim]not installed[/dim]", status
        )

    console.print(table)


@app.command("update")
def deps_update() -> None:
    """Update all dependencies to latest compatible versions and pin exact versions in pyproject.toml."""
    from kaira.commands.project import install_packages

    deps = _read_pyproject_deps()
    if not deps:
        console.print("[yellow]No dependencies found in pyproject.toml[/yellow]")
        return

    pp = Path.cwd() / "pyproject.toml"
    content = pp.read_text(encoding="utf-8") if pp.exists() else ""

    updated: list[tuple[str, str, str]] = []
    names = [re.split(r"[><!=]", dep)[0].strip() for dep in deps]
    before = {name: _pin_version(name) or "unknown" for name in names}

    # One invocation for the whole set: a per-package resolver cannot backtrack
    # across the dependency graph and can leave incompatible versions behind.
    install_packages(deps, upgrade=True)

    for dep, pkg_name in zip(deps, names):
        old_ver = before[pkg_name]
        new_ver = _pin_version(pkg_name) or old_ver
        if new_ver == old_ver:
            continue
        updated.append((pkg_name, old_ver, new_ver))
        if content:
            content = re.sub(
                rf'"{re.escape(dep)}"',
                f'"{pkg_name}=={new_ver}"',
                content,
            )

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
    from kaira.config import get_venv_python

    python_exe = get_venv_python()
    result = subprocess.run(
        [python_exe, "-m", "pip_audit", "--format", "json"],
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
        console.print(
            Panel(
                "[green]✅ No known vulnerabilities found.[/green]",
                border_style="green",
            )
        )
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
        console.print(
            Panel(
                "[red]❌ HIGH/CRITICAL vulnerabilities found. Fix immediately.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)


def _try_pip_audit_module() -> bool:
    """Check if pip_audit is importable as a module.

    Returns:
        True if pip_audit module is available.
    """
    from kaira.config import get_venv_python

    python_exe = get_venv_python()
    if python_exe != sys.executable:
        try:
            res = subprocess.run(
                [python_exe, "-c", "import pip_audit"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return res.returncode == 0
        except Exception:
            return False
    else:
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
    package: Annotated[
        str, typer.Argument(help="Package to install (e.g. httpx or httpx==0.27.0)")
    ],
    dev: Annotated[bool, typer.Option("--dev", help="Add as a dev dependency")] = False,
) -> None:
    """Install a package and add it to pyproject.toml.

    Args:
        package: Package name or pinned spec (e.g. 'httpx' or 'httpx>=0.27.0').
        dev: If True, add to [project.optional-dependencies].dev instead.
    """
    from kaira.commands.project import install_packages

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
            r"(dev\s*=\s*\[)",
            rf'\1\n    "{pin}",',
            content,
        )
    else:
        # Add to [project.dependencies]
        content = re.sub(
            r"(dependencies\s*=\s*\[)",
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
        console.print(
            f"[red]Failed to uninstall {package}: {result.stderr.strip()}[/red]"
        )
        raise typer.Exit(1)

    # Remove from pyproject.toml
    pp = Path.cwd() / "pyproject.toml"
    if pp.exists():
        content = pp.read_text(encoding="utf-8")
        # Remove any line containing the package name in dependencies
        lines = content.splitlines(keepends=True)
        new_lines = [
            line
            for line in lines
            if not re.search(rf'"{re.escape(package)}[><=!@"]*"', line)
        ]
        pp.write_text("".join(new_lines), encoding="utf-8")

    console.print(
        Panel(
            f"[green]✅ {package} removed and unpinned from pyproject.toml[/green]",
            border_style="green",
        )
    )
