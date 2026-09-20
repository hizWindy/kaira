"""Docs command — documentation generation and status management."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from kaira.config import get_config
from kaira.console import console
from kaira.core.docs_render import (
    apply_docs_plan,
    build_docs_plan,
    get_docs_status,
)
from kaira.core.parser import camel_to_snake
from kaira.core.route_discovery import discover_routes
from kaira.core.theme import Theme, sym
from kaira.core.ui import data_table, spinner_context, with_summary
from kaira.commands.ux_helpers import print_next_steps

app = typer.Typer(help="Documentation generation and status management.")

# How each group is labelled in legacy AI doc generators if invoked
_KIND_LABEL = {
    "model": "generated CRUD",
    "system": "Kaira scaffolding",
    "custom": "custom router",
}


def _fallback_doc(group, fields: list[dict]) -> str:
    """Build legacy API markdown for a single route group."""
    lines = [f"## {group.name} — {_KIND_LABEL.get(group.kind, group.kind)}", ""]
    if fields:
        lines += [
            "### Fields",
            "",
            "| Name | Type | Required |",
            "|------|------|----------|",
        ]
        for f in fields:
            req = "No" if str(f.get("type", "")).startswith("Optional") else "Yes"
            lines.append(f"| `{f.get('name')}` | `{f.get('type')}` | {req} |")
        lines.append("")
    lines += [
        "### Endpoints",
        "",
        "| Method | Path | Auth | Description |",
        "|--------|------|------|-------------|",
    ]
    for endpoint in group.endpoints:
        detail = endpoint.summary or endpoint.description or "—"
        detail = detail.replace("|", "\\|").strip()
        auth = "🔒" if endpoint.auth_required else "—"
        lines.append(f"| {endpoint.method} | `{endpoint.path}` | {auth} | {detail} |")
    return "\n".join(lines)


@app.command("generate")
@with_summary
def docs_generate(
    target: Annotated[
        Optional[str],
        typer.Argument(help="Section/model to document (e.g. User). Omit for all."),
    ] = None,
    only: Annotated[
        Optional[str],
        typer.Option(
            "--only",
            help="Generate only specified document: models | endpoints | erd | config | readme",
        ),
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Target output directory (default: ./docs).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show the plan and write nothing.",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Non-interactive mode (overwrites silently, no prompts).",
        ),
    ] = False,
    source_only: Annotated[
        bool,
        typer.Option(
            "--source",
            help="Read routes from source instead of importing the app.",
        ),
    ] = False,
    custom_only: Annotated[
        bool,
        typer.Option("--custom", help="Document only hand-written routers."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f", help="Overwrite changed files without confirming."
        ),
    ] = False,
) -> None:
    """Generate documentation from project state.

    Renders model specifications, endpoint catalogs, ERD diagrams, configuration
    guides, and project README into markdown files.

    Examples
    --------
    kaira docs generate
    kaira docs generate User
    kaira docs generate --only readme
    kaira docs generate --only models
    kaira docs generate --only endpoints
    kaira docs generate --only erd
    kaira docs generate --only config
    kaira docs generate --output ./documentation
    kaira docs generate --dry-run
    """
    config = get_config()
    root = Path.cwd()
    out_dir = output or (root / "docs")

    # If --source or --custom or custom target router is specified (legacy compatibility)
    if source_only or custom_only:
        model_names: set[str] = {
            str(m.get("name")) for m in config.generated_models if m.get("name")
        }
        fields_by_model = {
            str(m.get("name")): m.get("fields", [])
            for m in config.generated_models
            if m.get("name")
        }
        groups, strategy = discover_routes(
            root,
            model_names,
            prefer_live=not source_only,
            api_prefix=f"/api/{getattr(config, 'api_version', 'v1')}",
        )
        if custom_only:
            groups = [g for g in groups if g.is_custom]
            if not groups:
                console.print(
                    "[dim]No custom routers found — every route is generated.[/dim]"
                )
                raise typer.Exit(0)
        if target:
            matched = [g for g in groups if g.name.lower() == target.lower()]
            if not matched:
                available = ", ".join(g.name for g in groups)
                console.print(
                    f"[bold red]✗[/bold red]  No route group named '{target}'. "
                    f"Available: {available}"
                )
                raise typer.Exit(1)
            groups = matched
            output_file = out_dir / f"{matched[0].name}.md"
        else:
            output_file = out_dir / "api.md"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        all_docs = [
            f"# API Documentation\n\n*Generated by Khaira — {sum(len(g.endpoints) for g in groups)} endpoints.*"
        ]
        for group in groups:
            all_docs.append(_fallback_doc(group, fields_by_model.get(group.name, [])))
        output_file.write_text("\n\n---\n\n".join(all_docs), encoding="utf-8")
        console.print(
            f"  [green]✅[/green] Documentation written to [cyan]{output_file}[/cyan]"
        )
        return

    # Check if a custom non-model route group was requested directly
    if target:
        model_names = {
            m.get("name", "").lower() for m in config.generated_models if m.get("name")
        }
        models_dir = root / config.models_dir
        disk_models = (
            {p.stem.lower() for p in models_dir.glob("*.py")}
            if models_dir.is_dir()
            else set()
        )
        is_known_model = (
            target.lower() in model_names
            or target.lower() in disk_models
            or camel_to_snake(target).lower() in disk_models
        )

        if not is_known_model:
            # Check if it matches a discovered route group
            groups, _ = discover_routes(root, prefer_live=False)
            matched = [g for g in groups if g.name.lower() == target.lower()]
            if matched:
                output_file = out_dir / f"{matched[0].name}.md"
                output_file.parent.mkdir(parents=True, exist_ok=True)
                doc_text = _fallback_doc(matched[0], [])
                output_file.write_text(doc_text, encoding="utf-8")
                console.print(
                    f"  [green]✅[/green] Documentation written to [cyan]{output_file}[/cyan]"
                )
                return
            if not is_known_model and groups:
                available = ", ".join(
                    sorted(
                        set(
                            list(g.name for g in groups)
                            + [m.get("name", "") for m in config.generated_models]
                        )
                    )
                )
                console.print(
                    f"[bold red]✗[/bold red]  No route group or model named '{target}'. "
                    f"Available: {available}"
                )
                raise typer.Exit(1)

    with spinner_context("Analyzing project state and building documentation plan..."):
        plans = build_docs_plan(
            root=root,
            config=config,
            target_model=target,
            only=only,
            output_dir=out_dir,
        )

    if not plans:
        console.print("[yellow]No documentation targets to generate.[/yellow]")
        return

    # Up to date check
    if not any(p.needs_write for p in plans) and not dry_run:
        ok = sym("OK")
        console.print(
            f"  [{Theme.SUCCESS}]{ok} Documentation is up to date.[/{Theme.SUCCESS}]"
        )
        return

    if dry_run:
        console.print(
            f"\n  [{Theme.PRIMARY}]Documentation Plan (--dry-run)[/{Theme.PRIMARY}]"
        )
        rows: list[list[str]] = []
        for p in plans:
            action = (
                "Create"
                if p.status == "new"
                else ("Update" if p.status == "changed" else "Unchanged")
            )
            status_style = (
                Theme.SUCCESS
                if p.status == "new"
                else (Theme.WARNING if p.status == "changed" else Theme.MUTED)
            )
            rows.append(
                [p.path.name, str(p.path), f"[{status_style}]{action}[/{status_style}]"]
            )
        data_table(
            ["Document", "Target Path", "Action"], rows, title="⚡ Khaira — Docs Plan"
        )
        return

    # Apply plan with interactive overwrite prompts
    written, skipped = apply_docs_plan(
        plans,
        force=force,
        quiet=quiet,
    )

    if written > 0:
        ok = sym("OK")
        console.print(
            f"\n  [{Theme.SUCCESS}]{ok} Generated {written} documentation file{'s' if written != 1 else ''}[/{Theme.SUCCESS}] "
            f"in [{Theme.PRIMARY}]{out_dir}[/{Theme.PRIMARY}]"
        )
        if skipped > 0:
            console.print(
                f"  [{Theme.MUTED}]Skipped {skipped} file{'s' if skipped != 1 else ''}.[/{Theme.MUTED}]"
            )

        print_next_steps(
            [
                "Review generated docs: kaira docs status",
                "Export OpenAPI spec: kaira api export --format json",
                "Generate Postman collection: kaira api postman",
            ],
            quiet=quiet,
        )


@app.command("status")
def docs_status(
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Target output directory to inspect (default: ./docs).",
        ),
    ] = None,
) -> None:
    """Report documentation freshness against project state (read-only).

    Checks each documentation file against current model definitions, routes,
    and configuration to report whether files are up to date or stale.

    Examples
    --------
    kaira docs status
    """
    root = Path.cwd()
    out_dir = output or (root / "docs")

    records = get_docs_status(root=root, output_dir=out_dir)

    table_rows: list[list[str]] = []
    stale_count = 0
    missing_count = 0

    for rec in records:
        doc = rec["document"]
        desc = rec.get("description", "")
        status = rec["status"]
        gen_at = rec["generated_at"]

        if "Up to date" in status:
            status_cell = f"[{Theme.SUCCESS}]✓ {status}[/{Theme.SUCCESS}]"
        elif "Stale" in status:
            status_cell = f"[{Theme.WARNING}]⚠ {status}[/{Theme.WARNING}]"
            stale_count += 1
        else:
            status_cell = f"[{Theme.ERROR}]✗ {status}[/{Theme.ERROR}]"
            missing_count += 1

        gen_cell = f"[{Theme.MUTED}]{gen_at}[/{Theme.MUTED}]"
        table_rows.append([f"[bold]{doc}[/bold]", desc, status_cell, gen_cell])

    data_table(
        headers=["Document Path", "Description / Purpose", "Freshness", "Generated At"],
        rows=table_rows,
        title="⚡ Khaira — Documentation Freshness Status",
    )

    if stale_count > 0 or missing_count > 0:
        warn = sym("WARN")
        console.print(
            f"\n  [{Theme.WARNING}]{warn} {stale_count + missing_count} document(s) need regeneration. "
            f"Run: [bold]kaira docs generate[/bold][/{Theme.WARNING}]"
        )
    else:
        ok = sym("OK")
        console.print(
            f"\n  [{Theme.SUCCESS}]{ok} All documentation files are up to date.[/{Theme.SUCCESS}]"
        )
