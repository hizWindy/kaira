"""Config command group — read/write .devflow.json settings."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from devflow.config import get_config, save_config
from devflow.console import console

app = typer.Typer(help="Manage Kaira project configuration.")

# Fields that can be get/set via the CLI
SETTABLE_KEYS = {
    "output_dir",
    "models_dir",
    "repositories_dir",
    "schemas_dir",
    "services_dir",
    "routers_dir",
    "default_tier",
    "ai_provider",
    "ai_model",
    "ai_api_key_env",
    "api_version",
    "db_type",
    "auth_type",
}


@app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key to set")],
    value: Annotated[str, typer.Argument(help="Value to assign")],
) -> None:
    """Set a configuration value in .devflow.json.

    Examples
    --------
    kaira config set default_tier simple
    kaira config set api_version v2
    kaira config set models_dir app/models
    """
    # Map API_VERSION to api_version for Phase 3 convenience
    norm_key = key.lower().replace("-", "_")
    if norm_key == "api_version":
        norm_key = "api_version"

    if norm_key not in SETTABLE_KEYS:
        console.print(
            f"[bold red]✗[/bold red]  Unknown config key '[bold]{key}[/bold]'.\n"
            f"[dim]Settable keys: {', '.join(sorted(SETTABLE_KEYS))}[/dim]"
        )
        raise typer.Exit(1)

    config = get_config()
    setattr(config, norm_key, value)
    save_config(config)
    console.print(
        f"[bold green]✓[/bold green]  [cyan]{norm_key}[/cyan] = [bold]{value}[/bold]"
    )


@app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="Config key to retrieve")],
) -> None:
    """Get a configuration value from .devflow.json.

    Examples
    --------
    kaira config get default_tier
    kaira config get api_version
    """
    norm_key = key.lower().replace("-", "_")
    config = get_config()
    if not hasattr(config, norm_key):
        console.print(
            f"[bold red]✗[/bold red]  Unknown config key '[bold]{key}[/bold]'."
        )
        raise typer.Exit(1)
    value = getattr(config, norm_key)
    console.print(f"[cyan]{norm_key}[/cyan] = [bold]{value}[/bold]")


@app.command("show")
def config_show() -> None:
    """Display the full Kaira project configuration."""
    config = get_config()

    from rich import box
    from devflow.core.theme import Theme

    table = Table(
        title="Kaira Configuration",
        box=box.SIMPLE_HEAD,
        border_style=Theme.PRIMARY,
    )
    table.add_column("Key", style=f"bold {Theme.PRIMARY}", no_wrap=True)
    table.add_column("Value", style="green")

    skip_keys = {"generated_models"}
    for key, value in config.to_dict().items():
        if key in skip_keys:
            continue
        table.add_row(key, str(value))

    console.print(table)

    # Models count
    n = len(config.generated_models)
    console.print(f"[dim]Tracked models: {n}[/dim]")


# ---------------------------------------------------------------------------
# Phase 5 — reset-onboarding command
# ---------------------------------------------------------------------------


@app.command("reset-onboarding")
def config_reset_onboarding() -> None:
    """Delete the global Kaira user config so first-run onboarding runs again.

    The onboarding wizard is shown once per machine on first invocation.
    Use this command to re-trigger it (e.g. after changing machines or
    wanting to review experience-level and telemetry preferences).

    Examples
    --------
    kaira config reset-onboarding
    """
    from devflow.commands.onboarding import reset_config, _CONFIG_FILE

    if _CONFIG_FILE.exists():
        reset_config()
        console.print(
            "[bold green]✓[/bold green]  Global Kaira config reset. "
            "Onboarding will run on next [cyan]devflow[/cyan] invocation."
        )
    else:
        console.print("[dim]No global config found — nothing to reset.[/dim]")
