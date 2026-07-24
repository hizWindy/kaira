"""Kaira unified prompt wrappers — all interactive input goes through here.

Wraps InquirerPy to provide a consistent look-and-feel across all Phase 5
commands.  Every prompt:
- Handles ``Ctrl+C`` with a clean "Cancelled." exit (no traceback).
- Degrades gracefully when stdin is not a TTY: raises with the exact CLI flag
  to pass instead of hanging.
- Masks secret input and never echoes the value back.

Phase 1–4 commands are NOT modified.
"""

from __future__ import annotations

import sys
from typing import Any, Sequence

import typer

from kaira.core.theme import Theme, is_interactive, sym

# ---------------------------------------------------------------------------
# InquirerPy availability guard
# ---------------------------------------------------------------------------

try:
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator
    from InquirerPy.utils import get_style

    _HAS_INQUIRERPY = True
except ImportError:
    _HAS_INQUIRERPY = False
    inquirer = None  # type: ignore[assignment]
    Choice = None  # type: ignore[assignment, misc]
    Separator = None  # type: ignore[assignment, misc]
    get_style = None  # type: ignore[assignment]


def _require_inquirerpy() -> None:
    """Raise a friendly error when InquirerPy is not installed."""
    if not _HAS_INQUIRERPY:
        from kaira.console import console

        console.print(
            f"[{Theme.ERROR}]InquirerPy is required for interactive prompts.[/{Theme.ERROR}]\n"
            "Install it with:  pip install InquirerPy"
        )
        raise typer.Exit(1)


def _non_tty_error(flag: str) -> None:
    """Print a Phase-4-style smart error for missing non-TTY flag, then exit."""
    from kaira.console import console

    warn = sym("WARN")
    console.print(
        f"[{Theme.WARNING}]{warn}  stdin is not a TTY — interactive prompts are not available.[/{Theme.WARNING}]\n"
        f"  Pass the required value via:  [{Theme.PRIMARY}]{flag}[/{Theme.PRIMARY}]"
    )
    raise typer.Exit(1)


def _handle_cancel() -> None:
    """Print a clean 'Cancelled.' message and exit — no traceback."""
    from kaira.console import console

    console.print(f"[{Theme.MUTED}]Cancelled.[/{Theme.MUTED}]")
    raise typer.Exit(0)


# ---------------------------------------------------------------------------
# Prompt style configuration
# ---------------------------------------------------------------------------

_STYLE_DICT: dict[str, str] = {
    "questionmark": f"fg:{Theme.ACCENT.split()[-1] if Theme.ACCENT else 'magenta'} bold",
    "answermark": "fg:green bold",
    "answer": "fg:white bold",
    "input": "fg:white",
    "question": "fg:white bold",
    "answered_question": "fg:grey bold",
    "instruction": "fg:grey",
    "long_instruction": "fg:grey",
    "pointer": "fg:cyan bold",
    "checkbox": "fg:cyan",
    "separator": "fg:grey",
    "skipped": "fg:grey",
    "validator": "fg:red",
    "marker": "fg:cyan bold",
    "fuzzy_prompt": "fg:cyan",
    "fuzzy_info": "fg:grey",
    "fuzzy_border": "fg:grey",
    "fuzzy_match": "fg:cyan bold",
}

if _HAS_INQUIRERPY:
    _STYLE = get_style(_STYLE_DICT, style_override=False)
else:
    _STYLE = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public prompt API
# ---------------------------------------------------------------------------


def select(
    message: str,
    choices: Sequence[str | tuple[str, str]],
    *,
    default: str | None = None,
    flag: str = "--option",
) -> str:
    """Arrow-key single selection prompt with optional descriptions.

    Args:
        message: Question shown to the user.
        choices: Either plain strings or ``(name, description)`` tuples.
                 Descriptions are shown right-aligned in a muted second column.
        default: Default selected option name.
        flag: CLI flag shown in non-TTY error message.

    Returns:
        The selected option name string.

    Raises:
        typer.Exit: On Ctrl+C or non-TTY stdin without provided value.
    """
    _require_inquirerpy()
    if not is_interactive() or not sys.stdin.isatty():
        _non_tty_error(flag)

    # Build InquirerPy Choice objects with descriptions
    built_choices: list[Any] = []
    for ch in choices:
        if isinstance(ch, tuple):
            name, desc = ch
            built_choices.append(
                Choice(
                    value=name, name=f"{name:<30} [{Theme.MUTED}]{desc}[/{Theme.MUTED}]"
                )
            )
        else:
            built_choices.append(Choice(value=ch, name=ch))

    prompt = inquirer.select(  # type: ignore[union-attr]
        message=message,
        choices=built_choices,
        default=default,
        style=_STYLE,  # type: ignore[arg-type]
        pointer=sym("POINTER"),
        qmark="?",
    )

    @prompt.register_kb("escape")
    def _handle_escape(event: Any) -> None:
        event.app.exit(result=None)

    try:
        result = prompt.execute()
    except KeyboardInterrupt:
        _handle_cancel()

    if result is None:
        _handle_cancel()

    return str(result)


def multi_select(
    message: str,
    choices: Sequence[str | tuple[str, str]],
    *,
    default: Sequence[str] | None = None,
    flag: str = "--options",
) -> list[str]:
    """Arrow-key multi-selection checkbox prompt.

    Args:
        message: Question shown to the user.
        choices: Either plain strings or ``(name, description)`` tuples.
        default: List of pre-selected option names.
        flag: CLI flag shown in non-TTY error message.

    Returns:
        List of selected option name strings.

    Raises:
        typer.Exit: On Ctrl+C or non-TTY stdin without provided value.
    """
    _require_inquirerpy()
    if not is_interactive() or not sys.stdin.isatty():
        _non_tty_error(flag)

    built_choices: list[Any] = []
    for ch in choices:
        if isinstance(ch, tuple):
            name, desc = ch
            enabled = default and name in default
            built_choices.append(
                Choice(value=name, name=f"{name:<30} {desc}", enabled=bool(enabled))
            )
        else:
            enabled = default and ch in default
            built_choices.append(Choice(value=ch, name=ch, enabled=bool(enabled)))

    try:
        result = inquirer.checkbox(  # type: ignore[union-attr]
            message=message,
            choices=built_choices,
            style=_STYLE,  # type: ignore[arg-type]
            pointer=sym("POINTER"),
            qmark="?",
        ).execute()
    except KeyboardInterrupt:
        _handle_cancel()

    return list(result)


def confirm(
    message: str,
    *,
    default: bool = False,
    flag: str = "--yes/--no",
) -> bool:
    """Yes/No confirmation prompt.

    Args:
        message: Question shown to the user.
        default: Default answer (True = Yes).
        flag: CLI flag shown in non-TTY error message.

    Returns:
        True if confirmed, False otherwise.

    Raises:
        typer.Exit: On Ctrl+C or non-TTY stdin without provided value.
    """
    _require_inquirerpy()
    if not is_interactive() or not sys.stdin.isatty():
        _non_tty_error(flag)

    try:
        result = inquirer.confirm(  # type: ignore[union-attr]
            message=message,
            default=default,
            style=_STYLE,  # type: ignore[arg-type]
            qmark="?",
        ).execute()
    except KeyboardInterrupt:
        _handle_cancel()

    return bool(result)


def text(
    message: str,
    *,
    default: str = "",
    validate: Any = None,
    flag: str = "--value",
) -> str:
    """Free-text input prompt.

    Args:
        message: Question shown to the user.
        default: Default text value.
        validate: Optional InquirerPy validator or callable.
        flag: CLI flag shown in non-TTY error message.

    Returns:
        Entered string value.

    Raises:
        typer.Exit: On Ctrl+C or non-TTY stdin without provided value.
    """
    _require_inquirerpy()
    if not is_interactive() or not sys.stdin.isatty():
        _non_tty_error(flag)

    kwargs: dict[str, Any] = {
        "message": message,
        "default": default,
        "style": _STYLE,
        "qmark": "?",
    }
    if validate is not None:
        kwargs["validate"] = validate

    try:
        result = inquirer.text(**kwargs).execute()
    except KeyboardInterrupt:
        _handle_cancel()

    return str(result)


def secret(
    message: str,
    *,
    validate: Any = None,
    flag: str = "--secret",
) -> str:
    """Masked secret input prompt — value never echoed back.

    Args:
        message: Question shown to the user (e.g. "Database password:").
        validate: Optional InquirerPy validator or callable.
        flag: CLI flag shown in non-TTY error message.

    Returns:
        The entered secret string (never printed to console).

    Raises:
        typer.Exit: On Ctrl+C or non-TTY stdin without provided value.
    """
    _require_inquirerpy()
    if not is_interactive() or not sys.stdin.isatty():
        _non_tty_error(flag)

    kwargs: dict[str, Any] = {
        "message": message,
        "style": _STYLE,
        "qmark": "?",
    }
    if validate is not None:
        kwargs["validate"] = validate

    try:
        result = inquirer.secret(**kwargs).execute()
    except KeyboardInterrupt:
        _handle_cancel()

    return str(result)


def fuzzy_select(
    message: str,
    choices: Sequence[str | tuple[str, str]],
    *,
    default: str = "",
    flag: str = "--option",
) -> str:
    """Fuzzy-search prompt for long lists (>8 items).

    Uses InquirerPy's fuzzy prompt which provides live filtering as the
    user types.

    Args:
        message: Question shown to the user.
        choices: Either plain strings or ``(name, description)`` tuples.
        default: Default search text.
        flag: CLI flag shown in non-TTY error message.

    Returns:
        The selected option name string.

    Raises:
        typer.Exit: On Ctrl+C or non-TTY stdin without provided value.
    """
    _require_inquirerpy()
    if not is_interactive() or not sys.stdin.isatty():
        _non_tty_error(flag)

    built_choices: list[Any] = []
    for ch in choices:
        if isinstance(ch, tuple):
            name, desc = ch
            built_choices.append(Choice(value=name, name=f"{name}  —  {desc}"))
        else:
            built_choices.append(ch)

    prompt = inquirer.fuzzy(  # type: ignore[union-attr]
        message=message,
        choices=built_choices,
        default=default,
        style=_STYLE,  # type: ignore[arg-type]
        pointer=sym("POINTER"),
        qmark="?",
    )

    @prompt.register_kb("escape")
    def _handle_escape_fuzzy(event: Any) -> None:
        event.app.exit(result=None)

    try:
        result = prompt.execute()
    except KeyboardInterrupt:
        _handle_cancel()

    if result is None:
        _handle_cancel()

    return str(result)
