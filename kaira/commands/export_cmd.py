"""Data export command group — CLI pulls and generated API export endpoints.

Two trust boundaries, one pipeline. ``kaira export data`` is the developer's
own ad hoc pull; ``kaira export add`` generates a self-serve endpoint for the
*users* of the scaffolded app. Both read rows and serialize them through
:mod:`kaira.core.export`, so neither can drift into a weaker sensitive-field
rule than the other.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from kaira.commands.smart_errors import smart_error
from kaira.commands.ux_helpers import append_history, require_project
from kaira.config import get_config
from kaira.console import console
from kaira.core import export as export_core
from kaira.core.drivers import get_engine_driver
from kaira.core.export import (
    EXPORT_FORMATS,
    ExportDependencyError,
    ExportError,
)
from kaira.core.license import FEATURE_EXPORT_API, is_pro_enabled
from kaira.core.parser import camel_to_snake, snake_to_pascal, table_name

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

EXPORTS_DIR = "exports"

#: Runtime packages the *generated* app needs once an export endpoint exists.
GENERATED_EXPORT_PACKAGES = ("openpyxl", "reportlab", "python-docx")

#: Default cap for the generated endpoint — deliberately tighter than the
#: 60/minute of a normal GET, since one export reads a whole table.
DEFAULT_EXPORT_RATE_LIMIT = "5/minute"

# Marker pairs delimiting everything `kaira export add` writes into an existing
# file. Removal is then mechanical and total — including the imports, which is
# the part a hand-rolled removal always leaves behind.
ROUTER_IMPORTS_MARKERS = ("# [KAIRA_EXPORT_IMPORTS]", "# [/KAIRA_EXPORT_IMPORTS]")
ROUTER_ROUTE_MARKERS = ("# [KAIRA_EXPORT_ROUTE]", "# [/KAIRA_EXPORT_ROUTE]")
SERVICE_IMPORTS_MARKERS = (
    "# [KAIRA_EXPORT_SERVICE_IMPORTS]",
    "# [/KAIRA_EXPORT_SERVICE_IMPORTS]",
)
SERVICE_METHOD_MARKERS = ("    # [KAIRA_EXPORT_METHOD]", "    # [/KAIRA_EXPORT_METHOD]")

app = typer.Typer(help="Export data to xlsx/pdf/docx — CLI files and API endpoints.")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_env() -> Environment:
    # Autoescape stays off: these templates render Python source, not HTML.
    return Environment(  # nosec B701
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _validate_format(fmt: str, *, allow_all: bool = False) -> str:
    """Normalise and validate a ``--format`` value, or exit with a smart error."""
    normalized = (fmt or "").strip().lower()
    valid = list(EXPORT_FORMATS) + (["all"] if allow_all else [])
    if normalized not in valid:
        smart_error(
            context=f"Unsupported export format '{fmt}'.",
            typed=fmt,
            candidates=valid,
            fix_cmd=f"kaira export data MyModel --format {EXPORT_FORMATS[0]}",
            guide_topic="export",
        )
    return normalized


def _registered_models(config: Any) -> list[str]:
    """Every model name tracked in ``.kaira.json``."""
    return [m["name"] for m in getattr(config, "generated_models", []) if m.get("name")]


def _resolve_model(config: Any, model_name: str) -> str:
    """Confirm a model is tracked, or exit with a Did-You-Mean error."""
    known = _registered_models(config)
    if model_name in known:
        return model_name
    smart_error(
        context=f"Model '{model_name}' is not registered in this project.",
        typed=model_name,
        candidates=known,
        fix_cmd=f'kaira generate model {model_name} --fields "name:str"',
        guide_topic="export",
    )
    return model_name  # unreachable — smart_error exits


def _parse_key_values(raw: str | None, flag: str) -> dict[str, str]:
    """Parse the ``"key:value,key:value"`` grammar shared across Kaira flags.

    Values may contain a colon (a timestamp, a URL); only the first one
    separates key from value.
    """
    if not raw:
        return {}
    parsed: dict[str, str] = {}
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        if ":" not in item:
            smart_error(
                context=f"Invalid {flag} syntax — expected key:value pairs.",
                typed=item,
                fix_cmd=f'kaira export data User {flag} "status:active,role:admin"',
                guide_topic="export",
            )
        key, value = item.split(":", 1)
        key = key.strip()
        if not key:
            smart_error(
                context=f"Invalid {flag} syntax — missing field name.",
                typed=item,
                fix_cmd=f'kaira export data User {flag} "status:active"',
                guide_topic="export",
            )
        parsed[key] = value.strip()
    return parsed


def _parse_field_list(raw: str | None) -> list[str] | None:
    """Parse ``--fields "name,email"`` into an allowlist, or None for all."""
    if not raw:
        return None
    fields = [f.strip() for f in raw.split(",") if f.strip()]
    return fields or None


def _database_url() -> str:
    """Resolve the active DATABASE_URL with the same precedence as ``kaira db``."""
    from kaira.commands.db_cmd import _get_database_url

    return _get_database_url()


def _ensure_exports_dir(output_root: Path) -> Path:
    """Create ``exports/`` and keep it out of git.

    Exported files are real customer data sitting in the working tree — the
    one category of generated file that must never reach a remote, so the
    ignore entry is written at the same moment the directory appears.
    """
    exports = output_root / EXPORTS_DIR
    exports.mkdir(parents=True, exist_ok=True)
    _ensure_gitignored(output_root, f"{EXPORTS_DIR}/")
    return exports


def _ensure_gitignored(output_root: Path, pattern: str) -> None:
    """Append *pattern* to the project's .gitignore when it is not already there."""
    gitignore = output_root / ".gitignore"
    try:
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if any(line.strip() == pattern for line in existing.splitlines()):
            return
        prefix = "" if (not existing or existing.endswith("\n")) else "\n"
        gitignore.write_text(
            f"{existing}{prefix}\n# Khaira — exported data files, never commit\n{pattern}\n",
            encoding="utf-8",
        )
        console.print(
            f"  [green bold]✓[/green bold]  Added [cyan]{pattern}[/cyan] to .gitignore"
        )
    except OSError:
        console.print(
            f"[yellow]⚠  Could not update .gitignore — add '{pattern}' by hand.[/yellow]"
        )


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _offer_install(missing: ExportDependencyError) -> bool:
    """Offer to install a missing writer library through the Rich installer.

    Returns:
        True when the package was installed and the export can be retried.
    """
    console.print(
        Panel(
            f"[yellow]The .{missing.format} writer needs [bold]{missing.package}[/bold], "
            "which is not installed.[/yellow]",
            border_style="yellow",
            expand=False,
        )
    )
    if not typer.confirm(f"Install {missing.package} now?", default=True):
        console.print(
            f"[dim]Skipped. Install it later with:[/dim] "
            f"[cyan]kaira deps add {missing.package}[/cyan]"
        )
        return False

    from kaira.commands.project import install_packages

    installed, failed, _skipped = install_packages([missing.package])
    return installed > 0 and failed == 0


def _run_export(coro_factory: Any) -> Any:
    """Run an export coroutine, retrying once if a writer library was missing.

    The retry rebuilds the coroutine from scratch: an async generator that has
    already raised cannot be resumed, and the row iterators inside it are
    single-use.
    """
    try:
        return asyncio.run(coro_factory())
    except ExportDependencyError as missing:
        if not _offer_install(missing):
            raise typer.Exit(1) from missing
        return asyncio.run(coro_factory())


def _fail(message: str, *, fix: str = "") -> None:
    """Render an export failure and exit."""
    body = f"[red]❌ {message}[/red]"
    if fix:
        body += f"\n\n[dim]Fix:[/dim]  [bold green]{fix}[/bold green]"
    console.print(
        Panel(body, title="[red]Kaira Error[/red]", border_style="red", expand=False)
    )
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# FEATURE A — kaira export data
# ---------------------------------------------------------------------------


def _confirm_bulk_production_export(project_name: str, force: bool) -> bool:
    """Require the project name to be typed before a bulk export in production.

    Phase 4's :func:`~kaira.commands.ux_helpers.typed_confirmation` refuses
    outright when ``APP_ENV=production`` — correct there, because every caller
    destroys data. A bulk export destroys nothing, so blocking it would just
    push the operator to a raw ``psql`` dump with no redaction at all. What it
    borrows is the friction and the rule that ``--force`` buys nothing in
    production: pulling every row of PII out of a live database should be a
    deliberate act, not a flag.
    """
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env != "production":
        return True

    console.print(
        Panel(
            "[yellow]⚠️  Bulk export of every model from a [bold]production[/bold] database.\n"
            "This pulls personal data out of a live system into local files.[/yellow]",
            border_style="yellow",
            expand=False,
        )
    )
    console.print(
        f"  Type [bold]{project_name}[/bold] to confirm, or press Enter to abort:"
    )
    answer = typer.prompt("", default="")
    if answer.strip() != project_name:
        console.print("[dim]Aborted.[/dim]")
        return False
    if force:
        console.print(
            "[dim]--force is ignored in production — the confirmation above is the gate.[/dim]"
        )
    return True


def _fetch(config: Any, model: str, url: str, **kwargs: Any) -> Any:
    """Build a row iterator for *model* using the project's database paradigm."""
    driver = get_engine_driver(getattr(config, "db_type", "sqlite"))
    return export_core.fetch_rows(
        model,
        url=url,
        table=table_name(model),
        is_document_db=driver.is_document_db,
        **kwargs,
    )


@app.command("data")
def export_data(
    model_name: Annotated[
        str | None, typer.Argument(help="PascalCase model to export, e.g. User")
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: xlsx, pdf or docx.")
    ] = "xlsx",
    export_all: Annotated[
        bool, typer.Option("--all", help="Export every registered model.")
    ] = False,
    output: Annotated[
        str | None,
        typer.Option(
            "--output", help="Output file (single model) or directory (--all)."
        ),
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Maximum rows to export.")
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option("--fields", help='Comma-separated allowlist, e.g. "name,email".'),
    ] = None,
    filter_expr: Annotated[
        str | None,
        typer.Option(
            "--filter", help='Equality filters, e.g. "status:active,role:admin".'
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Skip prompts (never in production).")
    ] = False,
) -> None:
    """Export table data to a local file.

    Sensitive fields (password, token, secret, api_key…) are stripped from every
    export and there is no flag to keep them.

    Examples
    --------
    kaira export data User --format xlsx
    kaira export data User --format pdf --limit 100 --fields "username,email"
    kaira export data User --format docx --filter "status:active"
    kaira export data --all --format xlsx
    """
    require_project()
    config = get_config()
    output_root = Path.cwd() / config.output_dir
    fmt = _validate_format(fmt)

    if export_all and model_name:
        _fail(
            "Pass either a model name or --all, not both.",
            fix=f"kaira export data --all --format {fmt}",
        )
    if not export_all and not model_name:
        _fail(
            "Nothing to export — name a model or pass --all.",
            fix=f"kaira export data User --format {fmt}",
        )

    models = (
        _registered_models(config)
        if export_all
        else [_resolve_model(config, str(model_name))]
    )
    if not models:
        _fail(
            "No models are registered in this project yet.",
            fix='kaira generate model User --fields "username:str, email:str"',
        )

    if export_all and not _confirm_bulk_production_export(Path.cwd().name, force):
        raise typer.Exit(1)

    url = _database_url()
    if not url:
        _fail("No DATABASE_URL is configured for this project.", fix="kaira db connect")

    field_list = _parse_field_list(fields)
    filters = _parse_key_values(filter_expr, "--filter")

    append_history(
        "export data",
        {
            "models": ",".join(models),
            "format": fmt,
            "limit": str(limit) if limit else "",
            "fields": fields or "",
            "filter": filter_expr or "",
        },
    )

    exports_dir = _ensure_exports_dir(output_root)
    stamp = _timestamp()

    try:
        if export_all and fmt == "xlsx":
            written = _export_all_workbook(
                config,
                models,
                url,
                exports_dir,
                output,
                stamp,
                field_list,
                filters,
                limit,
            )
        else:
            written = _export_per_model(
                config,
                models,
                url,
                exports_dir,
                output,
                stamp,
                fmt,
                field_list,
                filters,
                limit,
                single=not export_all,
            )
    except ExportError as exc:
        _fail(str(exc))
        return

    _print_summary(written)


def _export_all_workbook(
    config: Any,
    models: list[str],
    url: str,
    exports_dir: Path,
    output: str | None,
    stamp: str,
    field_list: list[str] | None,
    filters: dict[str, str],
    limit: int | None,
) -> list[tuple[str, Path, int]]:
    """``--all --format xlsx`` — one workbook, one sheet per model."""
    target = Path(output) if output else exports_dir / f"export_{stamp}.xlsx"
    if output and target.is_dir():
        target = target / f"export_{stamp}.xlsx"
    target.parent.mkdir(parents=True, exist_ok=True)

    async def run() -> dict[str, int]:
        sheets = {
            model: _fetch(
                config, model, url, fields=field_list, filters=filters, limit=limit
            )
            for model in models
        }
        return await export_core.write_xlsx_workbook(sheets, str(target))

    counts = _run_export(run)
    return [(model, target, counts.get(model, 0)) for model in models]


def _export_per_model(
    config: Any,
    models: list[str],
    url: str,
    exports_dir: Path,
    output: str | None,
    stamp: str,
    fmt: str,
    field_list: list[str] | None,
    filters: dict[str, str],
    limit: int | None,
    *,
    single: bool,
) -> list[tuple[str, Path, int]]:
    """One file per model — every ``--all`` pdf/docx run, and every single export.

    A pdf or docx is a flat document: two models in one file would be two
    unrelated tables with no way to tell where one ends, so ``--all`` fans out
    into one file each instead.
    """
    written: list[tuple[str, Path, int]] = []
    for model in models:
        snake = camel_to_snake(model)
        if single and output:
            target = Path(output)
            if target.is_dir():
                target = target / f"{snake}_{stamp}.{fmt}"
        elif output:
            target = Path(output) / f"{snake}_{stamp}.{fmt}"
        else:
            target = exports_dir / f"{snake}_{stamp}.{fmt}"
        target.parent.mkdir(parents=True, exist_ok=True)

        async def run(model: str = model, target: Path = target) -> int:
            rows = _fetch(
                config, model, url, fields=field_list, filters=filters, limit=limit
            )
            return await export_core.write_rows(
                rows, fmt, str(target), f"{model} export"
            )

        written.append((model, target, _run_export(run)))
    return written


def _print_summary(written: list[tuple[str, Path, int]]) -> None:
    """Render what was exported, where, and how many rows."""
    table = Table(title="⚡ Khaira — Export Complete", border_style="cyan")
    table.add_column("Model", style="bold cyan")
    table.add_column("Rows", justify="right", style="green")
    table.add_column("File", style="dim")

    total = 0
    for model, path, count in written:
        total += count
        try:
            shown = path.relative_to(Path.cwd())
        except ValueError:
            shown = path
        table.add_row(model, str(count), str(shown))

    console.print()
    console.print(table)
    console.print(
        f"\n[dim]{total} record(s) exported. Sensitive fields "
        "(password, token, secret, api_key) were stripped.[/dim]"
    )


# ---------------------------------------------------------------------------
# FEATURE B — generated API export endpoints
# ---------------------------------------------------------------------------


def _router_path(config: Any, model: str, output_root: Path) -> Path:
    return output_root / config.routers_dir / f"{camel_to_snake(model)}_router.py"


def _service_path(config: Any, model: str, output_root: Path) -> Path:
    return output_root / config.services_dir / f"{camel_to_snake(model)}_service.py"


def _has_block(content: str, markers: tuple[str, str]) -> bool:
    return markers[0] in content and markers[1] in content


def _strip_block(content: str, markers: tuple[str, str]) -> str:
    """Remove a marked block, its markers, and the blank space it leaves behind."""
    start, end = markers
    pattern = re.compile(
        rf"\n*{re.escape(start)}.*?{re.escape(end)}[^\n]*\n?",
        re.DOTALL,
    )
    return pattern.sub("\n", content)


def _insert_after_imports(content: str, block: str) -> str:
    """Splice an import block in after the module's last top-level import.

    Appending imports at the end of the file would work for Python but trips
    ruff's E402 and reads as an accident; this keeps the generated file looking
    like the rest of the scaffold.
    """
    lines = content.splitlines(keepends=True)
    last = 0
    for index, line in enumerate(lines):
        if line.startswith(("from ", "import ")):
            last = index
    lines.insert(last + 1, "\n" + block.rstrip("\n") + "\n")
    return "".join(lines)


def _copy_shared_core(output_root: Path) -> list[Path]:
    """Copy the export pipeline into the generated project.

    The generated app cannot import Kaira, so the two modules are copied rather
    than re-implemented — same bytes, same sensitive-field rule, one place to
    fix. Always overwritten so a project cannot be left running an older copy
    of the strip logic than the CLI it was generated by.
    """
    core_dir = output_root / "core"
    core_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / "__init__.py").touch(exist_ok=True)

    written: list[Path] = []
    source_dir = Path(__file__).parent.parent / "core"
    for name in ("security.py", "export.py"):
        target = core_dir / name
        target.write_text(
            (source_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
        written.append(target)
    return written


def _ensure_rate_limit_setting(output_root: Path) -> bool:
    """Add ``EXPORT_RATE_LIMIT`` to the project's settings if it is missing.

    Written into the project rather than into Kaira's settings template so a
    project generated before Phase 7 gets the setting too, and no earlier-phase
    template has to change.

    Returns:
        True when the setting was added.
    """
    settings_file = output_root / "config" / "settings.py"
    if not settings_file.exists():
        return False
    content = settings_file.read_text(encoding="utf-8")
    if "EXPORT_RATE_LIMIT" in content:
        return False

    anchor = '    RATE_LIMIT_WRITE: str = "20/minute"\n'
    addition = (
        "    # One export reads an entire table — capped well below a normal GET.\n"
        f'    EXPORT_RATE_LIMIT: str = "{DEFAULT_EXPORT_RATE_LIMIT}"\n'
    )
    if anchor in content:
        content = content.replace(anchor, anchor + addition, 1)
    else:
        content = content.replace(
            "    DEBUG: bool = False\n", addition + "    DEBUG: bool = False\n", 1
        )
    settings_file.write_text(content, encoding="utf-8")
    return True


def _detect_auth_guard(router_content: str) -> bool:
    """Whether the model's router already depends on an auth guard."""
    return "get_current_user" in router_content


def _render(name: str, ctx: dict[str, Any]) -> str:
    return _get_env().get_template(name).render(**ctx)


def _format_generated(paths: list[Path]) -> None:
    """Run the project's ruff pass over files this command rewrote.

    Reuses ``generate``'s formatter so an injected block is indistinguishable
    from a freshly scaffolded one.
    """
    from kaira.commands.generate import _ruff_format

    for path in paths:
        _ruff_format(path)


@app.command("add")
def export_add(
    model_name: Annotated[str, typer.Argument(help="PascalCase model, e.g. User")],
    fmt: Annotated[
        str,
        typer.Option("--format", help="Format(s) to offer: xlsx, pdf, docx or all."),
    ] = "xlsx",
    rate_limit: Annotated[
        str | None,
        typer.Option("--rate-limit", help="Override the endpoint rate limit."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Regenerate an endpoint that already exists."),
    ] = False,
) -> None:
    """Generate a GET /export endpoint on an existing model's router.

    The endpoint reuses the model's existing auth guard and streams the file —
    it never buffers the table server-side, and never returns raw exception
    details to the client.

    Examples
    --------
    kaira export add User --format xlsx
    kaira export add Order --format all
    """
    require_project()
    # The seam a future "API generation is Pro, CLI export is free" split would
    # use. Always True in Phase 7 — no paywall is enforced.
    if not is_pro_enabled(FEATURE_EXPORT_API):  # pragma: no cover — stub is always True
        _fail("Generated export endpoints require a Kaira Pro license.")

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    fmt = _validate_format(fmt, allow_all=True)
    formats = list(EXPORT_FORMATS) if fmt == "all" else [fmt]
    model = _resolve_model(config, model_name)

    router_file = _router_path(config, model, output_root)
    service_file = _service_path(config, model, output_root)
    if not router_file.exists():
        _fail(
            f"No router found for {model}.",
            fix=f'kaira generate model {model} --fields "name:str"',
        )
    if not service_file.exists():
        _fail(
            f"No service layer found for {model} — export endpoints need one.",
            fix=f"kaira generate model {model} --tier full",
        )

    router_content = router_file.read_text(encoding="utf-8")
    if not _detect_auth_guard(router_content):
        smart_error(
            context=(
                f"This model has no auth layer — the {model} router is unguarded. "
                "Export endpoints are auth-gated by default and there is no opt-out."
            ),
            typed=f"kaira export add {model}",
            fix_cmd=f"kaira auth add-guard {model}",
            guide_topic="auth",
        )

    if _has_block(router_content, ROUTER_ROUTE_MARKERS) and not force:
        console.print(
            f"[yellow]⚠  {model} already has an export endpoint.[/yellow]\n"
            f"  Regenerate it with [bold]kaira export add {model} --format {fmt} --force[/bold], "
            f"or remove it with [bold]kaira export remove {model}[/bold]."
        )
        raise typer.Exit(1)

    driver = get_engine_driver(getattr(config, "db_type", "sqlite"))
    snake = camel_to_snake(model)
    ctx: dict[str, Any] = {
        "model_name": model,
        "snake_name": snake,
        "table_name": table_name(model),
        "formats": formats,
        "format_literal": ", ".join(f'"{f}"' for f in formats),
        "default_format": formats[0],
        "is_document_db": driver.is_document_db,
        "models_dir": config.models_dir,
        "rate_limit_setting": "settings.EXPORT_RATE_LIMIT",
    }

    # Regenerating means replacing: strip any previous blocks first so --force
    # cannot stack two endpoints with the same path on one router.
    for markers in (ROUTER_ROUTE_MARKERS, ROUTER_IMPORTS_MARKERS):
        router_content = _strip_block(router_content, markers)
    service_content = service_file.read_text(encoding="utf-8")
    for markers in (SERVICE_METHOD_MARKERS, SERVICE_IMPORTS_MARKERS):
        service_content = _strip_block(service_content, markers)

    router_content = _insert_after_imports(
        router_content, _render("export_router_imports.py.j2", ctx)
    )
    router_content = (
        router_content.rstrip("\n")
        + "\n\n\n"
        + _render("export_router_route.py.j2", ctx)
    )
    router_file.write_text(router_content, encoding="utf-8")

    service_content = _insert_after_imports(
        service_content, _render("export_service_imports.py.j2", ctx)
    )
    service_content = (
        service_content.rstrip("\n")
        + "\n\n"
        + _render("export_service_method.py.j2", ctx)
    )
    service_file.write_text(service_content, encoding="utf-8")

    copied = _copy_shared_core(output_root)
    added_setting = _ensure_rate_limit_setting(output_root)
    _ensure_export_requirements(output_root)

    if rate_limit:
        _apply_rate_limit_override(output_root, rate_limit)

    _format_generated([router_file, service_file])

    console.print(
        f"  [green bold]✓[/green bold]  Export endpoint added to [cyan]{router_file}[/cyan]"
    )
    console.print(
        f"  [green bold]✓[/green bold]  Export method added to [cyan]{service_file}[/cyan]"
    )
    for path in copied:
        console.print(
            f"  [green bold]✓[/green bold]  Shared pipeline: [cyan]{path}[/cyan]"
        )
    if added_setting:
        console.print(
            f"  [green bold]✓[/green bold]  EXPORT_RATE_LIMIT "
            f"([cyan]{rate_limit or DEFAULT_EXPORT_RATE_LIMIT}[/cyan]) added to config/settings.py"
        )

    api_version = getattr(config, "api_version", "v1")
    console.print(
        Panel(
            f"[green]GET /api/{api_version}/{snake}s/export?format={formats[0]}[/green]\n\n"
            f"  Formats:     [cyan]{', '.join(formats)}[/cyan]\n"
            f"  Auth:        [green]required[/green] (reuses this router's existing guard)\n"
            f"  Rate limit:  [cyan]{rate_limit or DEFAULT_EXPORT_RATE_LIMIT}[/cyan]\n"
            f"  Header:      [cyan]X-Kaira-Export-Format[/cyan]\n\n"
            f"[dim]Install the writer libraries in your project env:[/dim]\n"
            f"  [cyan]pip install {' '.join(GENERATED_EXPORT_PACKAGES)}[/cyan]",
            title="Khaira — Export Endpoint",
            border_style="green",
            expand=False,
        )
    )
    append_history("export add", {"model": model, "format": fmt})


def _apply_rate_limit_override(output_root: Path, rate_limit: str) -> None:
    """Point EXPORT_RATE_LIMIT at a caller-supplied value."""
    settings_file = output_root / "config" / "settings.py"
    if not settings_file.exists():
        return
    content = settings_file.read_text(encoding="utf-8")
    updated = re.sub(
        r'(EXPORT_RATE_LIMIT: str = )"[^"]*"',
        rf'\1"{rate_limit}"',
        content,
        count=1,
    )
    if updated != content:
        settings_file.write_text(updated, encoding="utf-8")


def _ensure_export_requirements(output_root: Path) -> None:
    """Record the writer libraries in the project's requirements.txt."""
    req = output_root / "requirements.txt"
    if not req.exists():
        return
    try:
        content = req.read_text(encoding="utf-8")
        missing = [p for p in GENERATED_EXPORT_PACKAGES if p not in content]
        if not missing:
            return
        prefix = "" if content.endswith("\n") or not content else "\n"
        req.write_text(
            content
            + prefix
            + "\n# Kaira export endpoints\n"
            + "\n".join(missing)
            + "\n",
            encoding="utf-8",
        )
    except OSError:  # pragma: no cover — requirements is a convenience
        pass


_FORMAT_LITERAL_RE = re.compile(r"format:\s*Literal\[([^\]]+)\]")
_RATE_LIMIT_RE = re.compile(r'@limiter\.limit\((settings\.EXPORT_RATE_LIMIT|"[^"]+")\)')


def _extract_block(content: str, markers: tuple[str, str]) -> str:
    """Return the text between a marker pair, or an empty string.

    Every reader works on the extracted block rather than the whole file — a
    router has several ``@limiter.limit`` decorators, and matching the first
    one reports the create endpoint's limit as the export endpoint's.
    """
    start, end = markers
    match = re.search(rf"{re.escape(start)}(.*?){re.escape(end)}", content, re.DOTALL)
    return match.group(1) if match else ""


@app.command("list")
def export_list() -> None:
    """List every model with a generated export endpoint.

    Read from the router files themselves rather than from ``.kaira.json``:
    the source is what actually serves traffic, so a hand-edited router shows
    up here honestly instead of being contradicted by a stale snapshot.
    """
    require_project()
    config = get_config()
    output_root = Path.cwd() / config.output_dir
    routers_dir = output_root / config.routers_dir

    rate_limit_default = _configured_rate_limit(output_root)

    rows: list[tuple[str, str, bool, str]] = []
    if routers_dir.is_dir():
        for router_file in sorted(routers_dir.glob("*_router.py")):
            content = router_file.read_text(encoding="utf-8")
            block = _extract_block(content, ROUTER_ROUTE_MARKERS)
            if not block:
                continue
            model = snake_to_pascal(router_file.stem.removesuffix("_router"))
            match = _FORMAT_LITERAL_RE.search(block)
            formats = (
                ", ".join(f.strip().strip('"') for f in match.group(1).split(","))
                if match
                else "—"
            )
            limit_match = _RATE_LIMIT_RE.search(block)
            limit = limit_match.group(1) if limit_match else "—"
            if limit == "settings.EXPORT_RATE_LIMIT":
                limit = rate_limit_default
            # Read the guard off the export endpoint itself, not the file: a
            # sibling CRUD route being guarded says nothing about this one.
            rows.append((model, formats, _detect_auth_guard(block), limit.strip('"')))

    if not rows:
        console.print(
            Panel(
                "[dim]No export endpoints generated yet.[/dim]\n\n"
                "  Add one with [bold cyan]kaira export add User --format xlsx[/bold cyan]",
                title="⚡ Khaira — Export Endpoints",
                border_style="cyan",
                expand=False,
            )
        )
        return

    table = Table(title="⚡ Khaira — Export Endpoints", border_style="cyan")
    table.add_column("Model", style="bold cyan")
    table.add_column("Formats", style="green")
    table.add_column("Auth-gated", justify="center")
    table.add_column("Rate limit", style="yellow")
    for model, formats, guarded, limit in rows:
        table.add_row(model, formats, "✅" if guarded else "❌", limit)
    console.print(table)


def _configured_rate_limit(output_root: Path) -> str:
    """Read EXPORT_RATE_LIMIT out of the project's settings, or the default."""
    settings_file = output_root / "config" / "settings.py"
    if settings_file.exists():
        match = re.search(
            r'EXPORT_RATE_LIMIT:\s*str\s*=\s*"([^"]+)"',
            settings_file.read_text(encoding="utf-8"),
        )
        if match:
            return match.group(1)
    return DEFAULT_EXPORT_RATE_LIMIT


@app.command("remove")
def export_remove(
    model_name: Annotated[str, typer.Argument(help="PascalCase model, e.g. User")],
) -> None:
    """Remove a generated export endpoint, imports included.

    Examples
    --------
    kaira export remove User
    """
    require_project()
    config = get_config()
    output_root = Path.cwd() / config.output_dir
    model = model_name

    router_file = _router_path(config, model, output_root)
    service_file = _service_path(config, model, output_root)

    removed: list[Path] = []
    for path, marker_pairs in (
        (router_file, (ROUTER_ROUTE_MARKERS, ROUTER_IMPORTS_MARKERS)),
        (service_file, (SERVICE_METHOD_MARKERS, SERVICE_IMPORTS_MARKERS)),
    ):
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        original = content
        for markers in marker_pairs:
            content = _strip_block(content, markers)
        if content != original:
            path.write_text(content.rstrip("\n") + "\n", encoding="utf-8")
            removed.append(path)

    if not removed:
        console.print(
            f"[yellow]⚠  No generated export endpoint found for {model}.[/yellow]\n"
            "  List what exists with [bold]kaira export list[/bold]."
        )
        raise typer.Exit(1)

    _format_generated(removed)
    for path in removed:
        console.print(
            f"  [green bold]✓[/green bold]  Export block removed from [cyan]{path}[/cyan]"
        )
    console.print(
        Panel(
            f"[green]{model} export endpoint removed.[/green]\n\n"
            "[dim]core/export.py and core/security.py are left in place — other\n"
            "models may still be using them.[/dim]",
            title="Khaira — Export",
            border_style="green",
            expand=False,
        )
    )
    append_history("export remove", {"model": model})
