"""Rendering, drift detection, and sync for the generated Docker surface.

Everything that turns :mod:`kaira.core.docker_state` into files on disk lives
here — rendering, comparing what is on disk against what the templates would
produce now, and the interactive overwrite flow.

Splitting this out from ``commands/docker_cmd.py`` is what lets the auto-sync
prompt be called from ``cache init``, ``task init``, ``integrate``, and
``db switch`` without any of them importing the Docker command module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.text import Text

from kaira.console import console
from kaira.core import docker_state
from kaira.core.detector import compute_diff
from kaira.core.docker_state import DEV, PROD, ProjectState
from kaira.core.theme import Theme, is_interactive

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

DOCKERFILE = "Dockerfile"
DOCKERIGNORE = ".dockerignore"
COMPOSE_DEV = "docker-compose.yml"
COMPOSE_PROD = "docker-compose.prod.yml"

COMPOSE_FILES = (COMPOSE_DEV, COMPOSE_PROD)


def _yaml_flow(value: object) -> str:
    """Render *value* as a YAML flow sequence, e.g. ``["CMD", "redis-cli"]``.

    Jinja's built-in ``tojson`` is HTML-safe, so it escapes apostrophes to
    ``\\u0027``.  That is still valid YAML but makes an inline Python healthcheck
    unreadable, so compose lists go through plain :func:`json.dumps` instead.
    """
    return json.dumps(value)


def get_jinja_env() -> Environment:
    """Return the Jinja environment used for every Docker template."""
    env = Environment(  # nosec B701 - generating Dockerfiles/YAML, not HTML
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["yaml_flow"] = _yaml_flow
    return env


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_files(
    state: ProjectState,
    *,
    with_compose: bool,
) -> dict[str, str]:
    """Render the Docker surface for *state*.

    Args:
        state: Resolved project state.
        with_compose: Whether compose files are part of this project's surface.
            A Dockerfile-only project renders no compose files at all rather
            than empty ones.

    Returns:
        Mapping of project-relative filename → rendered content.
    """
    env = get_jinja_env()
    # The Dockerfile has no per-environment differences; dev context is fine.
    base_ctx = docker_state.build_context(state, DEV)

    rendered: dict[str, str] = {
        DOCKERFILE: env.get_template("docker_dockerfile.j2").render(**base_ctx),
        DOCKERIGNORE: env.get_template("docker_ignore.j2").render(**base_ctx),
    }

    if with_compose:
        rendered[COMPOSE_DEV] = env.get_template("docker_compose.j2").render(**base_ctx)
        rendered[COMPOSE_PROD] = env.get_template("docker_compose_prod.j2").render(
            **docker_state.build_context(state, PROD)
        )

    return rendered


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


@dataclass
class FilePlan:
    """One file's current state versus what the templates would produce now."""

    path: Path
    content: str
    status: str  # "new" | "changed" | "same"

    @property
    def needs_write(self) -> bool:
        """True when writing this file would change the working tree."""
        return self.status != "same"

    def diff(self) -> str:
        """Return a unified diff of on-disk content against the new content."""
        try:
            existing = self.path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        return compute_diff(existing, self.content, self.path.name)


def docker_enabled(root: Optional[Path] = None) -> bool:
    """True when the project has a generated Dockerfile."""
    root = Path.cwd() if root is None else root
    return (root / DOCKERFILE).is_file()


def compose_enabled(root: Optional[Path] = None) -> bool:
    """True when the project has generated compose files."""
    root = Path.cwd() if root is None else root
    return any((root / name).is_file() for name in COMPOSE_FILES)


def build_plan(
    root: Optional[Path] = None,
    *,
    state: Optional[ProjectState] = None,
    with_compose: Optional[bool] = None,
) -> list[FilePlan]:
    """Compare the project's Docker files against freshly rendered output.

    Args:
        root: Project root; defaults to the current working directory.
        state: Pre-resolved state; resolved from *root* when omitted.
        with_compose: Force compose files in or out of the plan.  When omitted,
            compose is included only if the project already has compose files.

    Returns:
        One :class:`FilePlan` per file in the project's Docker surface.
    """
    root = Path.cwd() if root is None else root
    state = docker_state.resolve_state(root) if state is None else state
    if with_compose is None:
        with_compose = compose_enabled(root)

    plans: list[FilePlan] = []
    for name, content in render_files(state, with_compose=with_compose).items():
        path = root / name
        if not path.is_file():
            status = "new"
        else:
            try:
                status = (
                    "same" if path.read_text(encoding="utf-8") == content else "changed"
                )
            except OSError:
                status = "changed"
        plans.append(FilePlan(path=path, content=content, status=status))
    return plans


def is_out_of_sync(root: Optional[Path] = None) -> bool:
    """True when any generated Docker file differs from current project state.

    Returns ``False`` for projects with no Dockerfile at all — nothing to drift.
    """
    root = Path.cwd() if root is None else root
    if not docker_enabled(root):
        return False
    return any(plan.needs_write for plan in build_plan(root))


# ---------------------------------------------------------------------------
# Interactive sync
# ---------------------------------------------------------------------------

_STATUS_STYLE = {
    "new": Theme.SUCCESS,
    "changed": Theme.WARNING,
    "same": Theme.MUTED,
}


def _prompt_action(plan: FilePlan) -> str:
    """Ask what to do about one changed file: ``o``, ``s``, or ``v``.

    Mirrors the Phase 4 UX5 prompt so the Docker surface behaves like every
    other place Kaira is about to overwrite something the user may have edited.
    """
    try:
        import questionary

        choice = questionary.select(
            f"Action for {plan.path.name}:",
            choices=[
                {"name": "overwrite", "value": "o"},
                {"name": "skip", "value": "s"},
                {"name": "view full file", "value": "v"},
            ],
            default="s",
        ).ask()
        if choice in {"o", "s", "v"}:
            return str(choice)
    except Exception:  # noqa: BLE001 - fall back to the plain prompt
        pass

    console.print(
        Text.from_markup(
            "\n  [bold cyan]o[/bold cyan] Overwrite  "
            "[bold blue]s[/bold blue] Skip  "
            "[bold magenta]v[/bold magenta] View full file\n"
        )
    )
    return str(Prompt.ask("[bold]Action[/bold]", choices=["o", "s", "v"], default="s"))


def show_diff(plan: FilePlan) -> None:
    """Print a syntax-highlighted diff for *plan*."""
    diff_text = plan.diff()
    if not diff_text.strip():
        return
    console.print(
        Panel(
            Syntax(diff_text, "diff", theme="monokai", line_numbers=True),
            title=f"[{Theme.PRIMARY}]Diff: {plan.path.name}[/{Theme.PRIMARY}]",
            border_style=Theme.BORDER_PRIMARY,
        )
    )


def apply_plan(
    plans: list[FilePlan],
    *,
    force: bool = False,
    quiet: bool = False,
) -> tuple[int, int]:
    """Write the files in *plans*, prompting before replacing existing ones.

    New files are always written — there is nothing to lose.  Changed files go
    through the diff/overwrite prompt unless *force* or *quiet* is set.

    Args:
        plans: Plans to apply; ``same`` entries are skipped.
        force: Overwrite changed files without prompting.
        quiet: Non-interactive mode for CI — overwrites silently.

    Returns:
        ``(written, skipped)`` counts.
    """
    written = 0
    skipped = 0

    for plan in plans:
        if not plan.needs_write:
            continue

        if plan.status == "new" or force or quiet or not is_interactive():
            plan.path.parent.mkdir(parents=True, exist_ok=True)
            plan.path.write_text(plan.content, encoding="utf-8")
            written += 1
            continue

        show_diff(plan)
        while True:
            choice = _prompt_action(plan)
            if choice == "v":
                console.print(
                    Panel(
                        Syntax(
                            plan.content, "yaml", theme="monokai", line_numbers=True
                        ),
                        title=f"[{Theme.ACCENT}]Full file: {plan.path.name}[/{Theme.ACCENT}]",
                        border_style=Theme.ACCENT,
                    )
                )
                continue
            if choice == "o":
                plan.path.write_text(plan.content, encoding="utf-8")
                written += 1
            else:
                skipped += 1
            break

    return written, skipped


# ---------------------------------------------------------------------------
# Auto-sync hook — called by commands that change project state
# ---------------------------------------------------------------------------


def maybe_autosync(*, quiet: bool = False, root: Optional[Path] = None) -> bool:
    """Offer to regenerate Docker files after a project-state change.

    Called by every command that changes what Docker should contain (cache
    init, task init, integrate, db switch).  Does nothing when the project has
    no Dockerfile, when nothing actually drifted, or when *quiet* is set — in
    which case the user is pointed at ``kaira docker sync`` instead, because a
    silent rewrite is the wrong default for a scripted run.

    Args:
        quiet: Suppress the prompt and regenerate nothing.
        root: Project root; defaults to the current working directory.

    Returns:
        True when files were regenerated.
    """
    root = Path.cwd() if root is None else root
    if not docker_enabled(root):
        return False

    plans = build_plan(root)
    pending = [plan for plan in plans if plan.needs_write]
    if not pending:
        return False

    names = ", ".join(plan.path.name for plan in pending)

    if quiet or not is_interactive():
        console.print(
            f"  [{Theme.MUTED}]Docker configuration is out of sync ({names}). "
            f"Run: kaira docker sync[/{Theme.MUTED}]"
        )
        return False

    console.print(
        f"\n  [{Theme.WARNING}]Docker configuration is out of sync[/{Theme.WARNING}] "
        f"[{Theme.MUTED}]({names})[/{Theme.MUTED}]"
    )
    answer = Prompt.ask(
        "  Regenerate?", choices=["y", "n"], default="y", show_choices=True
    )
    if answer != "y":
        console.print(
            f"  [{Theme.MUTED}]Skipped. Run `kaira docker sync` when ready.[/{Theme.MUTED}]"
        )
        return False

    written, _ = apply_plan(pending, force=True)
    console.print(
        f"  [{Theme.SUCCESS}]Docker configuration regenerated[/{Theme.SUCCESS}] "
        f"[{Theme.MUTED}]({written} file{'s' if written != 1 else ''})[/{Theme.MUTED}]"
    )
    return True
