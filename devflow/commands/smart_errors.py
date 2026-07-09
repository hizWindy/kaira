"""Smart error messages for DevFlow CLI — structured errors with Did You Mean, fix commands, and guide references."""

from __future__ import annotations

from typing import Optional

import typer
from rich.panel import Panel

from devflow.console import console
from devflow.commands.ux_helpers import suggest_did_you_mean


def smart_error(
    *,
    context: str,
    typed: Optional[str] = None,
    candidates: Optional[list[str]] = None,
    likely: Optional[str] = None,
    fix_cmd: Optional[str] = None,
    guide_topic: Optional[str] = None,
    exit_code: int = 1,
) -> None:
    """Display a structured error message and exit.

    Shows what went wrong, what the user typed, Did You Mean suggestions,
    a copy-pasteable fix command, and a relevant guide command.

    Args:
        context: Human-readable description of the error.
        typed: The value the user actually provided.
        candidates: Valid options to fuzzy-match against.
        likely: Explicit 'Did you mean?' value (overrides fuzzy match).
        fix_cmd: Copy-pasteable corrective command.
        guide_topic: Topic for 'devflow guide <topic>' hint.
        exit_code: Exit code to use (default 1).
    """
    lines: list[str] = [f"[red]❌ {context}[/red]"]

    if typed:
        lines.append(f"\n[dim]You typed:[/dim]  [yellow]{typed}[/yellow]")

    # Did You Mean?
    suggestions: list[str] = []
    if likely:
        suggestions = [likely]
    elif typed and candidates:
        suggestions = suggest_did_you_mean(typed, candidates)

    if suggestions:
        joined = ", ".join(f"[bold cyan]{s}[/bold cyan]" for s in suggestions)
        lines.append(f"[dim]Did you mean?[/dim]  {joined}")

    if candidates and not suggestions:
        opts = ", ".join(f"[cyan]{c}[/cyan]" for c in candidates[:8])
        lines.append(f"[dim]Supported values:[/dim]  {opts}")

    if fix_cmd:
        lines.append(f"\n[dim]Fix:[/dim]  [bold green]{fix_cmd}[/bold green]")

    if guide_topic:
        lines.append(f"[dim]Guide:[/dim]  [bold]devflow guide {guide_topic}[/bold]")

    console.print(
        Panel(
            "\n".join(lines),
            title="[red]DevFlow Error[/red]",
            border_style="red",
            expand=False,
        )
    )
    raise typer.Exit(exit_code)


# ---------------------------------------------------------------------------
# Named error factories for common scenarios
# ---------------------------------------------------------------------------


def error_invalid_model_name(name: str) -> None:
    """Report an invalid model name — must be PascalCase.

    Args:
        name: The invalid name the user provided.
    """
    smart_error(
        context="Invalid model name — model names must be PascalCase (e.g. UserProfile, BlogPost).",
        typed=name,
        fix_cmd=f"devflow generate model {name.capitalize()}",
        guide_topic="generate",
    )


def error_invalid_field_type(field_name: str, field_type: str) -> None:
    """Report an unsupported field type.

    Args:
        field_name: The field whose type is invalid.
        field_type: The invalid type string.
    """
    from devflow.config import SUPPORTED_FIELD_TYPES

    smart_error(
        context=f"Unsupported field type '{field_type}' for field '{field_name}'.",
        typed=field_type,
        candidates=sorted(SUPPORTED_FIELD_TYPES),
        fix_cmd=f'devflow generate model MyModel --fields "{field_name}:str"',
        guide_topic="generate",
    )


def error_invalid_relation_syntax(detail: str) -> None:
    """Report an invalid relation syntax.

    Args:
        detail: Description of the syntax problem.
    """
    smart_error(
        context=f"Invalid relation syntax: {detail}",
        fix_cmd='devflow add relation Post --has-many Comment --cascade "all, delete-orphan"',
        guide_topic="generate",
    )


def error_missing_auth_layer() -> None:
    """Report that no auth layer is set up when one is required."""
    smart_error(
        context="No authentication layer is configured for this project.",
        fix_cmd="devflow auth generate --type jwt",
        guide_topic="auth",
    )


def error_migrate_on_mongodb() -> None:
    """Report that migrations are not supported on MongoDB projects."""
    smart_error(
        context="Alembic migrations are not supported for MongoDB projects.",
        typed="devflow migrate ...",
        fix_cmd="devflow guide db",
        guide_topic="db",
    )


def error_missing_devflow_json() -> None:
    """Report that .devflow.json is missing for a project-scoped command."""
    smart_error(
        context="This command requires a DevFlow project (.devflow.json not found).",
        fix_cmd="devflow init <project-name>",
        guide_topic="init",
    )
