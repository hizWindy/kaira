"""Config command group — read/write .devflow.json settings."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from devflow.config import get_config, save_config, DevFlowConfig
from devflow.console import console

app = typer.Typer(help="Manage DevFlow project configuration.")

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
    devflow config set default_tier simple
    devflow config set api_version v2
    devflow config set models_dir app/models
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
    console.print(f"[bold green]✓[/bold green]  [cyan]{norm_key}[/cyan] = [bold]{value}[/bold]")


@app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="Config key to retrieve")],
) -> None:
    """Get a configuration value from .devflow.json.

    Examples
    --------
    devflow config get default_tier
    devflow config get api_version
    """
    norm_key = key.lower().replace("-", "_")
    config = get_config()
    if not hasattr(config, norm_key):
        console.print(f"[bold red]✗[/bold red]  Unknown config key '[bold]{key}[/bold]'.")
        raise typer.Exit(1)
    value = getattr(config, norm_key)
    console.print(f"[cyan]{norm_key}[/cyan] = [bold]{value}[/bold]")


@app.command("show")
def config_show() -> None:
    """Display the full DevFlow project configuration."""
    config = get_config()

    table = Table(title="DevFlow Configuration", border_style="cyan", show_lines=True)
    table.add_column("Key", style="bold cyan", no_wrap=True)
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
