"""Smart error messages for Kaira CLI — structured errors with Did You Mean, fix commands, and guide references."""

from __future__ import annotations

from typing import Optional

import typer
from rich.panel import Panel

from kaira.console import console
from kaira.commands.ux_helpers import suggest_did_you_mean


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
        guide_topic: Topic for 'kaira guide <topic>' hint.
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
        lines.append(f"[dim]Guide:[/dim]  [bold]kaira guide {guide_topic}[/bold]")

    console.print(
        Panel(
            "\n".join(lines),
            title="[red]Kaira Error[/red]",
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
        fix_cmd=f"kaira generate model {name.capitalize()}",
        guide_topic="generate",
    )


def error_invalid_field_type(field_name: str, field_type: str) -> None:
    """Report an unsupported field type.

    Args:
        field_name: The field whose type is invalid.
        field_type: The invalid type string.
    """
    from kaira.config import SUPPORTED_FIELD_TYPES

    smart_error(
        context=f"Unsupported field type '{field_type}' for field '{field_name}'.",
        typed=field_type,
        candidates=sorted(SUPPORTED_FIELD_TYPES),
        fix_cmd=f'kaira generate model MyModel --fields "{field_name}:str"',
        guide_topic="generate",
    )


def error_invalid_relation_syntax(detail: str) -> None:
    """Report an invalid relation syntax.

    Args:
        detail: Description of the syntax problem.
    """
    smart_error(
        context=f"Invalid relation syntax: {detail}",
        fix_cmd='kaira add relation Post --has-many Comment --cascade "all, delete-orphan"',
        guide_topic="generate",
    )


def error_missing_auth_layer() -> None:
    """Report that no auth layer is set up when one is required."""
    smart_error(
        context="No authentication layer is configured for this project.",
        fix_cmd="kaira auth generate --type jwt",
        guide_topic="auth",
    )


def error_migrate_on_mongodb() -> None:
    """Report that migrations are not supported on MongoDB projects."""
    smart_error(
        context="Alembic migrations are not supported for MongoDB projects.",
        typed="kaira migrate ...",
        fix_cmd="kaira guide db",
        guide_topic="db",
    )


# Human-readable labels for document/schemaless databases that have no Alembic.
_DOCUMENT_DB_LABELS = {
    "mongodb": "MongoDB",
    "atlas": "MongoDB Atlas",
    "firebase": "Firebase (Firestore)",
    "firestore": "Firebase (Firestore)",
}


def error_migrate_on_document_db(db_type: str) -> None:
    """Report that migrations are not supported on a document/schemaless database.

    Covers MongoDB, MongoDB Atlas, and Firebase/Firestore projects, all of
    which are schemaless and therefore have no Alembic migration path.

    Args:
        db_type: The configured database type (e.g. ``"mongodb"``, ``"firebase"``).
    """
    label = _DOCUMENT_DB_LABELS.get(db_type.lower(), db_type)
    smart_error(
        context=f"Alembic migrations are not supported for {label} projects "
        "(schemaless — no migrations needed).",
        typed="kaira migrate ...",
        fix_cmd="kaira guide db",
        guide_topic="db",
    )


def error_missing_kaira_json() -> None:
    """Report that .kaira.json is missing for a project-scoped command."""
    smart_error(
        context="This command requires a Kaira project (.kaira.json not found).",
        fix_cmd="kaira init <project-name>",
        guide_topic="init",
    )
