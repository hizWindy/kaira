"""Kaira flags command group — feature flag management.

Generates core/flags.py with a FEATURE_FLAGS dict and is_enabled() function.
Flags must be snake_case. Unknown flags always return False (fail-closed).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from kaira.console import console

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Feature flag management.")

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _get_env_loader() -> Environment:
    """Return a Jinja2 environment for Kaira templates."""
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _flags_path(output_root: Path) -> Path:
    """Return the path to core/flags.py."""
    return output_root / "core" / "flags.py"


def _read_flags(flags_file: Path) -> dict[str, bool]:
    """Parse the FEATURE_FLAGS dict from an existing flags.py file."""
    if not flags_file.exists():
        return {}
    content = flags_file.read_text(encoding="utf-8")
    flags: dict[str, bool] = {}
    for match in re.finditer(r'"([^"]+)":\s*(True|False)', content):
        flags[match.group(1)] = match.group(2) == "True"
    return flags


def _write_flags(flags_file: Path, flags: dict[str, bool]) -> None:
    """Regenerate flags.py from the given flags dict."""
    flag_list = [{"name": k, "default": str(v).lower()} for k, v in flags.items()]
    jinja = _get_env_loader()
    tmpl = jinja.get_template("flags.py.j2")
    flags_file.write_text(
        tmpl.render(project_name=Path.cwd().name, flags=flag_list),
        encoding="utf-8",
    )


def _require_flags_file(output_root: Path) -> Path:
    """Assert that core/flags.py exists. Exit 1 if not."""
    fp = _flags_path(output_root)
    if not fp.exists():
        console.print(
            Panel(
                "[yellow]core/flags.py not found. Run: [cyan]kaira flags init[/cyan] first.[/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)
    return fp


@app.command("init")
def flags_init() -> None:
    """Initialise the feature flags module (core/flags.py)."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    (output_root / "core").mkdir(parents=True, exist_ok=True)
    fp = _flags_path(output_root)

    if fp.exists():
        console.print(
            "[yellow]core/flags.py already exists. Use kaira flags add to add flags.[/yellow]"
        )
        return

    _write_flags(fp, {})
    console.print(f"  [green]✅[/green] Generated: [cyan]{fp}[/cyan]")
    console.print(
        Panel(
            "[green]✅ Feature flags initialised.[/green]\n"
            "Add flags with: [cyan]kaira flags add <flag_name> --default false[/cyan]",
            border_style="green",
        )
    )


@app.command("add")
def flags_add(
    flag_name: Annotated[str, typer.Argument(help="snake_case flag name")],
    default: Annotated[
        str,
        typer.Option("--default", help="Default value: true | false"),
    ] = "false",
) -> None:
    """Add a new feature flag with a default value."""
    if not _SNAKE_CASE_RE.match(flag_name):
        console.print(
            Panel(
                f"[red]❌ Invalid flag name '{flag_name}'.\n"
                "Flag names must be snake_case (lowercase letters, digits, underscores).\n"
                "Example: my_feature_flag[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    default_bool = default.lower() in ("true", "1", "yes")

    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    fp = _require_flags_file(output_root)

    flags = _read_flags(fp)
    if flag_name in flags:
        console.print(
            f"[yellow]Flag '{flag_name}' already exists. Use enable/disable to change it.[/yellow]"
        )
        return

    flags[flag_name] = default_bool
    _write_flags(fp, flags)
    console.print(
        Panel(
            f"[green]✅ Flag '[bold]{flag_name}[/bold]' added (default: {default_bool}).[/green]",
            border_style="green",
        )
    )


@app.command("enable")
def flags_enable(
    flag_name: Annotated[str, typer.Argument(help="Flag name to enable")],
) -> None:
    """Enable a feature flag."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    fp = _require_flags_file(output_root)

    flags = _read_flags(fp)
    if flag_name not in flags:
        console.print(
            f"[red]❌ Flag '{flag_name}' not found. Add it with: kaira flags add {flag_name}[/red]"
        )
        raise typer.Exit(1)

    flags[flag_name] = True
    _write_flags(fp, flags)
    console.print(f"[green]✅ Flag '[bold]{flag_name}[/bold]' enabled.[/green]")


@app.command("disable")
def flags_disable(
    flag_name: Annotated[str, typer.Argument(help="Flag name to disable")],
) -> None:
    """Disable a feature flag."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    fp = _require_flags_file(output_root)

    flags = _read_flags(fp)
    if flag_name not in flags:
        console.print(
            f"[red]❌ Flag '{flag_name}' not found. Add it with: kaira flags add {flag_name}[/red]"
        )
        raise typer.Exit(1)

    flags[flag_name] = False
    _write_flags(fp, flags)
    console.print(f"[green]✅ Flag '[bold]{flag_name}[/bold]' disabled.[/green]")


@app.command("list")
def flags_list() -> None:
    """List all feature flags and their current state."""
    from kaira.config import get_config

    cfg = get_config()
    output_root = Path.cwd() / cfg.output_dir
    fp = _flags_path(output_root)

    if not fp.exists():
        console.print("[yellow]No flags file found. Run: kaira flags init[/yellow]")
        return

    flags = _read_flags(fp)
    if not flags:
        console.print("[dim]No flags defined yet. Use kaira flags add <name>.[/dim]")
        return

    table = Table(title="⚡ Feature Flags", border_style="cyan")
    table.add_column("Flag Name", style="bold")
    table.add_column("State")

    for name, enabled in sorted(flags.items()):
        state = "[green]✅ Enabled[/green]" if enabled else "[red]❌ Disabled[/red]"
        table.add_row(name, state)

    console.print(table)
    console.print("[dim]Unknown flags always return False (fail-closed).[/dim]")
