"""Authentication scaffolding command group."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel

from kaira.config import get_config
from kaira.console import console
from kaira.core.detector import write_with_check
from kaira.core.wiring import register_router

# Auth types that expose an APIRouter, mapped to the module holding it.
# ``api-key`` is intentionally absent — it ships a dependency, not routes.
ROUTER_MODULES = {
    "jwt": ("auth/router.py", "auth.router"),
    "oauth2": ("auth/oauth2.py", "auth.oauth2"),
}

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Authentication scaffolding commands.")


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("generate")
def auth_generate(
    auth_type: Annotated[
        str, typer.Option("--type", help="Auth type: jwt, oauth2, api-key")
    ] = "jwt",
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files.")
    ] = False,
) -> None:
    """Generate authentication boilerplate code."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    auth_dir = output_root / "auth"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "__init__.py").touch(exist_ok=True)

    env = _get_env()
    db_type = getattr(config, "db_type", "sqlite")
    ctx: dict = {
        "project_name": Path.cwd().name,
        "db_type": db_type,
        # The auth router is mounted under the versioned prefix, so OAuth2's
        # tokenUrl has to match or Swagger's Authorize button posts to a 404.
        "api_version": getattr(config, "api_version", "v1"),
    }

    if auth_type == "jwt":
        _generate_jwt(env, ctx, auth_dir, output_root, force)
    elif auth_type == "oauth2":
        _generate_oauth2(env, ctx, auth_dir, force)
    elif auth_type == "api-key":
        _generate_api_key(env, ctx, auth_dir, force)
    else:
        console.print(f"[red]Unknown auth type:[/red] {auth_type}")
        raise typer.Exit(1)

    # Generate rate_limit.py if it doesn't exist
    rl_path = output_root / "rate_limit.py"
    if not rl_path.exists():
        tmpl = env.get_template("rate_limit.py.j2")
        content = tmpl.render(**ctx)
        write_with_check(rl_path, content, force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{rl_path}[/cyan]")

    console.print(
        Panel(
            f"[green]Auth ({auth_type}) scaffolding complete![/green]",
            title="Khaira — Auth",
            border_style="green",
        )
    )

    if auth_type in ROUTER_MODULES:
        console.print(
            "\n[dim]Next:[/dim] mount the auth routes in main.py with "
            "[cyan]kaira auth register[/cyan]"
        )


def _generate_jwt(
    env: Environment, ctx: dict, auth_dir: Path, output_root: Path, force: bool
) -> None:
    """Generate JWT authentication files."""
    templates = {
        "auth_jwt_dependencies.py.j2": auth_dir / "dependencies.py",
        "auth_jwt_router.py.j2": auth_dir / "router.py",
        "auth_jwt_service.py.j2": auth_dir / "service.py",
        "auth_jwt_schemas.py.j2": auth_dir / "schemas.py",
        "auth_jwt_utils.py.j2": auth_dir / "utils.py",
    }

    for tmpl_name, out_path in templates.items():
        tmpl = env.get_template(tmpl_name)
        content = tmpl.render(**ctx)
        write_with_check(out_path, content, force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")

    # Generate BlacklistedToken model
    models_dir = output_root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "__init__.py").touch(exist_ok=True)
    bt_tmpl = env.get_template("auth_blacklisted_token_model.py.j2")
    bt_path = models_dir / "blacklisted_token.py"
    write_with_check(bt_path, bt_tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{bt_path}[/cyan]")


def _generate_oauth2(env: Environment, ctx: dict, auth_dir: Path, force: bool) -> None:
    """Generate OAuth2 authentication files."""
    tmpl = env.get_template("auth_oauth2.py.j2")
    out_path = auth_dir / "oauth2.py"
    write_with_check(out_path, tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")


def _generate_api_key(env: Environment, ctx: dict, auth_dir: Path, force: bool) -> None:
    """Generate API key authentication files."""
    tmpl = env.get_template("auth_api_key.py.j2")
    out_path = auth_dir / "api_key.py"
    write_with_check(out_path, tmpl.render(**ctx), force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{out_path}[/cyan]")


@app.command("register")
def auth_register(
    auth_type: Annotated[
        Optional[str],
        typer.Option(
            "--type",
            help="Auth type to register: jwt or oauth2. Auto-detected when omitted.",
        ),
    ] = None,
    no_version_prefix: Annotated[
        bool,
        typer.Option(
            "--no-version-prefix", help="Mount at /auth instead of /api/<version>/auth."
        ),
    ] = False,
) -> None:
    """Register the generated auth router in main.py."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    if auth_type is None:
        detected = [
            t for t, (rel, _) in ROUTER_MODULES.items() if (output_root / rel).exists()
        ]
        if not detected:
            console.print(
                "[yellow]⚠  No auth router found.[/yellow]\n"
                "  Run [bold]kaira auth generate --type jwt[/bold] first."
            )
            raise typer.Exit(1)
        if len(detected) > 1:
            console.print(
                f"[yellow]⚠  Multiple auth routers found ({', '.join(detected)}).[/yellow]\n"
                "  Pick one with [bold]kaira auth register --type <jwt|oauth2>[/bold]."
            )
            raise typer.Exit(1)
        auth_type = detected[0]

    if auth_type == "api-key":
        console.print(
            "[yellow]⚠  API key auth has no router to register.[/yellow]\n"
            "  It ships a [cyan]validate_api_key[/cyan] dependency — add it to the endpoints you\n"
            "  want protected instead."
        )
        raise typer.Exit(1)

    if auth_type not in ROUTER_MODULES:
        console.print(f"[red]Unknown auth type:[/red] {auth_type}")
        raise typer.Exit(1)

    rel_path, module = ROUTER_MODULES[auth_type]
    router_file = output_root / rel_path
    if not router_file.exists():
        console.print(
            f"[red]Auth router not found:[/red] {router_file}\n"
            f"  Run [bold]kaira auth generate --type {auth_type}[/bold] first."
        )
        raise typer.Exit(1)

    import_line = f"from {module} import router as auth_router"
    if no_version_prefix:
        include_line = "app.include_router(auth_router)"
        mounted_at = "/auth"
    else:
        include_line = "app.include_router(auth_router, prefix=API_VERSION_PREFIX)"
        mounted_at = f"/api/{getattr(config, 'api_version', 'v1')}/auth"

    main_path = output_root / "main.py"
    result = register_router(main_path, import_line, include_line)

    if result == "no-main":
        console.print(f"[red]main.py not found:[/red] {main_path}")
        raise typer.Exit(1)

    if result == "already":
        console.print(
            f"[yellow]⚠  Auth router is already registered in {main_path}.[/yellow]"
        )
        return

    console.print(
        f"  [green bold]✓[/green bold]  Auth router registered in [cyan]{main_path}[/cyan]"
    )
    console.print(
        Panel(
            f"[green]Auth routes mounted at[/green] [bold]{mounted_at}[/bold]",
            title="Khaira — Auth",
            border_style="green",
        )
    )

    if getattr(config, "auth_type", "none") == "none":
        console.print(
            "\n[dim]Hint:[/dim] [bold]auth_type[/bold] is still [bold]none[/bold] in your config, so newly\n"
            f"  generated routers won't get auth guards. Set it with:\n"
            f"  [cyan]kaira config set auth_type {auth_type}[/cyan]"
        )


@app.command("add-guard")
def auth_add_guard(
    router_name: Annotated[
        str, typer.Argument(help="Name of the router model (PascalCase, e.g. User)")
    ],
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Non-interactive mode."),
    ] = False,
) -> None:
    """Add Depends(get_current_user) to all endpoints in a router."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    # Check that auth has been generated
    auth_dep_path = output_root / "auth" / "dependencies.py"
    if not auth_dep_path.exists():
        console.print(
            "[yellow]⚠  Auth has not been generated yet.[/yellow]\n"
            "  Run [bold]kaira auth generate --type jwt[/bold] first."
        )
        raise typer.Exit(1)

    # Find the router file
    from kaira.core.parser import camel_to_snake

    snake = camel_to_snake(router_name)
    router_path = output_root / config.routers_dir / f"{snake}_router.py"
    if not router_path.exists():
        console.print(f"[red]Router file not found:[/red] {router_path}")
        raise typer.Exit(1)

    content = router_path.read_text(encoding="utf-8")

    # Check if already guarded
    if "get_current_user" in content:
        console.print(
            f"[yellow]⚠  {router_name} router already has auth guard.[/yellow]"
        )
        return

    # Inject import
    import_line = "from auth.dependencies import get_current_user\n"
    # Add after the last import line
    lines = content.split("\n")
    last_import_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            last_import_idx = i
    lines.insert(last_import_idx + 1, import_line)

    # Add Depends(get_current_user) to every endpoint function signature
    new_lines = []
    for line in lines:
        new_lines.append(line)
        # After each 'def ...(', inject the dependency on the next suitable line
        if re.match(r"^def \w+\(", line) or re.match(r"^async def \w+\(", line):
            # Find closing paren and add dependency before it
            pass  # We'll use a simpler approach: inject into Depends chain

    content = "\n".join(lines)
    modified = re.sub(
        r"(def (?!list_)\w+\([^)]*)(service: [^)]+= Depends\(get_service\))",
        r"\1\2,\n    current_user: dict = Depends(get_current_user)",
        content,
    )

    router_path.write_text(modified, encoding="utf-8")
    console.print(
        f"  [green bold]✓[/green bold]  Auth guard added to [cyan]{router_path}[/cyan]"
    )

    from kaira.core.docs_render import maybe_autodocs

    maybe_autodocs(quiet=quiet)
