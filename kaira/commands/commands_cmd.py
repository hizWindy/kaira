"""Kaira commands index command (Phase 7.5).

Provides a static, scannable index of every command registered in Kaira by
introspecting the root Typer app. Supports filtering by group (--group)
or keyword search (--search).
"""

from __future__ import annotations

from typing import Annotated, Optional

import typer

from kaira.console import console
from kaira.core.theme import Theme
from kaira.core.ui import render_small_banner

app = typer.Typer(
    help="Index of all available Kaira commands.",
    invoke_without_command=True,
)

# ---------------------------------------------------------------------------
# Category mapping rules (maps root command or group to a category)
# ---------------------------------------------------------------------------

_CATEGORY_MAP: dict[str, str] = {
    "init": "SCAFFOLDING",
    "generate": "SCAFFOLDING",
    "add": "SCAFFOLDING",
    "sync": "SCAFFOLDING",
    "list": "SCAFFOLDING",
    "diff": "SCAFFOLDING",
    "check": "SCAFFOLDING",
    "info": "SCAFFOLDING",
    "db": "DATABASE",
    "migrate": "DATABASE",
    "migrate-docs": "DATABASE",
    "cloud": "CLOUD",
    "auth": "SECURITY & AUTH",
    "audit": "SECURITY & AUTH",
    "env": "ENVIRONMENT",
    "test": "TESTING & QUALITY",
    "quality": "TESTING & QUALITY",
    "loadtest": "TESTING & QUALITY",
    "health": "TESTING & QUALITY",
    "health-endpoint": "TESTING & QUALITY",
    "deps": "OPERATIONS",
    "docker": "OPERATIONS",
    "ci": "OPERATIONS",
    "seed": "OPERATIONS",
    "version": "OPERATIONS",
    "websocket": "OPERATIONS",
    "cache": "OPERATIONS",
    "task": "OPERATIONS",
    "integrate": "OPERATIONS",
    "api": "OPERATIONS",
    "profile": "OPERATIONS",
    "deploy": "OPERATIONS",
    "middleware": "OPERATIONS",
    "event": "OPERATIONS",
    "notify": "OPERATIONS",
    "flags": "OPERATIONS",
    "run": "OPERATIONS",
    "recap": "OPERATIONS",
    "status": "OPERATIONS",
    "menu": "DISCOVERY",
    "guide": "DISCOVERY",
    "commands": "DISCOVERY",
    "about": "DISCOVERY",
}


def _clean_help(help_text: Optional[str]) -> str:
    """Extract first line of docstring / help text, stripping rich markup tags."""
    if not help_text:
        return "(no description)"
    first_line = help_text.strip().splitlines()[0].strip()
    # Basic cleanup of rich markup tags like [bold cyan]
    import re

    cleaned = re.sub(r"\[/?[\w\s=]+\]", "", first_line)
    return cleaned or "(no description)"


def introspect_typer_app(
    typer_instance: typer.Typer, prefix: str = ""
) -> list[tuple[str, str, str]]:
    """Recursively introspect a Typer app instance and return registered commands.

    Args:
        typer_instance: The Typer app to introspect.
        prefix: Current command prefix (e.g. ``"generate"``).

    Returns:
        List of ``(full_command_name, help_text, category)`` tuples.
    """
    results: list[tuple[str, str, str]] = []

    # Process registered commands
    for cmd_info in typer_instance.registered_commands:
        if cmd_info.hidden:
            continue
        cmd_name = cmd_info.name or (
            cmd_info.callback.__name__ if cmd_info.callback else ""
        )
        if not cmd_name:
            continue
        full_name = f"{prefix} {cmd_name}".strip() if prefix else cmd_name
        help_text = _clean_help(
            cmd_info.help or (cmd_info.callback.__doc__ if cmd_info.callback else None)
        )

        root_group = full_name.split()[0]
        cat = _CATEGORY_MAP.get(root_group, "OPERATIONS")
        results.append((full_name, help_text, cat))

    # Process registered sub-groups
    for group_info in typer_instance.registered_groups:
        if group_info.hidden or not group_info.typer_instance:
            continue
        group_name = group_info.name or ""
        sub_prefix = f"{prefix} {group_name}".strip() if prefix else group_name

        sub_results = introspect_typer_app(group_info.typer_instance, prefix=sub_prefix)
        results.extend(sub_results)

    return results


@app.callback(invoke_without_command=True)
def commands_main(
    ctx: typer.Context,
    group: Annotated[
        Optional[str],
        typer.Option(
            "--group",
            "-g",
            help="Filter by category (e.g. db, scaffolding, operations)",
        ),
    ] = None,
    search: Annotated[
        Optional[str],
        typer.Option(
            "--search",
            "-s",
            help="Filter by keyword across command names and descriptions",
        ),
    ] = None,
) -> None:
    """Display a scannable index of all registered Kaira commands."""
    render_small_banner()
    console.print()

    # Import root app dynamically to avoid circular import at module load
    from kaira.main import app as root_app

    all_commands = introspect_typer_app(root_app)
    # Deduplicate by command name while preserving order
    seen: set[str] = set()
    unique_commands: list[tuple[str, str, str]] = []
    for cmd_name, help_text, cat in all_commands:
        if cmd_name not in seen:
            seen.add(cmd_name)
            unique_commands.append((cmd_name, help_text, cat))

    # Apply group filter
    filtered = unique_commands
    if group:
        g_lower = group.lower()
        filtered = [
            c
            for c in filtered
            if g_lower in c[2].lower() or g_lower in c[0].split()[0].lower()
        ]

    # Apply search filter
    if search:
        s_lower = search.lower()
        filtered = [
            c for c in filtered if s_lower in c[0].lower() or s_lower in c[1].lower()
        ]

    if not filtered:
        console.print(
            f"[{Theme.WARNING}]No commands matched the given filter.[/{Theme.WARNING}]"
        )
        return

    # Group commands by category
    grouped: dict[str, list[tuple[str, str]]] = {}
    for cmd_name, help_text, cat in filtered:
        grouped.setdefault(cat, []).append((cmd_name, help_text))

    # Order categories logically
    category_order = [
        "SCAFFOLDING",
        "DATABASE",
        "CLOUD",
        "SECURITY & AUTH",
        "ENVIRONMENT",
        "TESTING & QUALITY",
        "OPERATIONS",
        "DISCOVERY",
    ]

    # Render groups
    for cat in category_order:
        if cat not in grouped:
            continue
        cmds = grouped[cat]
        console.print(f"  [{Theme.PRIMARY}]{cat}[/{Theme.PRIMARY}]")
        for cmd_name, help_text in cmds:
            desc_style = Theme.MUTED if help_text == "(no description)" else ""
            desc_str = (
                f"[{desc_style}]{help_text}[/{desc_style}]" if desc_style else help_text
            )
            console.print(f"    {cmd_name:<28} {desc_str}")
        console.print()

    # Shortcuts block (Phase shortcuts)
    if not group and not search:
        from kaira.core.ui import render_shortcuts_table

        render_shortcuts_table()
        console.print()

    # Footer
    total_count = len(unique_commands)
    shown_count = len(filtered)
    count_str = (
        f"{shown_count} commands"
        if shown_count == total_count
        else f"{shown_count}/{total_count} commands"
    )

    console.print(
        f"  [{Theme.MUTED}]{count_str} · kaira menu for interactive search[/{Theme.MUTED}]"
    )
    console.print(
        f"  [{Theme.MUTED}]            · kaira guide <topic> for examples[/{Theme.MUTED}]"
    )
    console.print()
