"""Change detection, diff display, and safe file writing for DevFlow."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Literal

import typer
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.text import Text

from devflow.console import console

OverwriteChoice = Literal["overwrite", "skip", "diff"]


# ---------------------------------------------------------------------------
# Existence check
# ---------------------------------------------------------------------------

def file_exists(path: Path) -> bool:
    """Return True if *path* exists on disk."""
    return path.is_file()


# ---------------------------------------------------------------------------
# Diff display
# ---------------------------------------------------------------------------

def compute_diff(existing_content: str, new_content: str, filename: str = "") -> str:
    """Return a unified diff string between existing and new content."""
    existing_lines = existing_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        existing_lines,
        new_lines,
        fromfile=f"existing/{filename}",
        tofile=f"generated/{filename}",
        lineterm="",
    )
    return "".join(diff)


def show_diff(existing_path: Path, new_content: str) -> None:
    """Display a colored diff between the existing file and *new_content*."""
    try:
        existing_content = existing_path.read_text(encoding="utf-8")
    except OSError:
        existing_content = ""

    diff_text = compute_diff(existing_content, new_content, existing_path.name)

    if not diff_text.strip():
        console.print(
            Panel(
                "[dim]No changes detected — generated output is identical.[/dim]",
                title=f"[bold cyan]Diff: {existing_path.name}[/bold cyan]",
                border_style="cyan",
            )
        )
        return

    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
    console.print(
        Panel(
            syntax,
            title=f"[bold cyan]Diff: {existing_path.name}[/bold cyan]",
            border_style="cyan",
        )
    )


# ---------------------------------------------------------------------------
# Interactive overwrite prompt
# ---------------------------------------------------------------------------

def prompt_overwrite(path: Path) -> OverwriteChoice:
    """Prompt the user for what to do when a file already exists.

    Returns one of: "overwrite", "skip", "diff".
    """
    try:
        import questionary
        choice = questionary.select(
            f"File already exists: {path}. Choose an action:",
            choices=[
                {"name": "overwrite", "value": "overwrite"},
                {"name": "skip", "value": "skip"},
                {"name": "show diff", "value": "diff"},
            ],
            default="skip",
        ).ask()
        if choice in ("overwrite", "skip", "diff"):
            return choice
    except Exception:
        pass

    console.print(
        Panel(
            Text.from_markup(
                f"[yellow]⚠[/yellow]  File already exists: [bold]{path}[/bold]\n"
                f"[dim]Choose an action:[/dim]\n"
                f"  [bold cyan]o[/bold cyan] — overwrite\n"
                f"  [bold blue]s[/bold blue] — skip\n"
                f"  [bold magenta]d[/bold magenta] — show diff",
            ),
            title="[bold yellow]File Conflict[/bold yellow]",
            border_style="yellow",
        )
    )
    while True:
        choice = Prompt.ask(
            "[bold]Your choice[/bold]",
            choices=["o", "s", "d"],
            default="s",
        )
        if choice == "o":
            return "overwrite"
        if choice == "s":
            return "skip"
        if choice == "d":
            return "diff"


# ---------------------------------------------------------------------------
# Safe write
# ---------------------------------------------------------------------------

def write_with_check(
    path: Path,
    content: str,
    force: bool = False,
    non_interactive: bool = False,
) -> Literal["written", "skipped"]:
    """Write *content* to *path*, respecting change detection.

    Parameters
    ----------
    path:
        Target file path.
    content:
        File content to write.
    force:
        If True, overwrite without prompting.
    non_interactive:
        If True, skip existing files without prompting.

    Returns
    -------
    "written" or "skipped".
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if not file_exists(path):
        _write(path, content)
        return "written"

    if force:
        _write(path, content)
        return "written"

    if non_interactive:
        console.print(f"  [yellow]⚠[/yellow]  Skipped (already exists): [dim]{path}[/dim]")
        return "skipped"

    # Interactive loop — user may choose "diff" multiple times before deciding
    while True:
        choice = prompt_overwrite(path)
        if choice == "diff":
            show_diff(path, content)
            # After showing diff, ask again
            continue
        if choice == "overwrite":
            _write(path, content)
            return "written"
        # "skip"
        console.print(f"  [blue]→[/blue]  Skipped: [dim]{path}[/dim]")
        return "skipped"


def _write(path: Path, content: str) -> None:
    """Low-level write with error handling."""
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        console.print(
            Panel(
                f"[red]✗[/red]  Failed to write [bold]{path}[/bold]\n"
                f"[dim]{exc}[/dim]",
                title="[bold red]Write Error[/bold red]",
                border_style="red",
            )
        )
        raise typer.Exit(1) from exc
