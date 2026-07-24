"""Kaira db command group — database connection, management, and utilities."""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from kaira.console import console
from kaira.commands.ux_helpers import mask_credentials, typed_confirmation

app = typer.Typer(help="Database connection, status, and management commands.")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DB_CLIENTS: dict[str, str] = {
    "postgresql": "psql",
    "mysql": "mysql",
    "mongodb": "mongosh",
    "sqlite": "sqlite3",
}

_DB_DRIVERS: dict[str, list[str]] = {
    "postgresql": ["asyncpg", "sqlalchemy[asyncio]"],
    "mysql": ["aiomysql", "sqlalchemy[asyncio]"],
    "mongodb": ["motor", "beanie"],
    "sqlite": ["aiosqlite", "sqlalchemy[asyncio]"],
}

_RELATIONAL = {"postgresql", "mysql", "sqlite"}


def _get_database_url() -> str:
    """Read DATABASE_URL from environment, active .env, or fallback to config/settings.py.

    Returns:
        Connection URL string.
    """
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        # Try reading from .env
        env_file = Path.cwd() / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("DATABASE_URL="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not raw:
        # Try reading from config/settings.py default fallback
        settings_file = Path.cwd() / "config" / "settings.py"
        if settings_file.exists():
            raw = _extract_setting_default(settings_file, "DATABASE_URL") or ""
    return raw


def _extract_setting_default(settings_file: Path, key: str) -> Optional[str]:
    """Extract a string-literal default for *key* from a settings module via AST.

    Parses ``config/settings.py`` with :mod:`ast` (never imports or executes it)
    and returns the first string-constant assigned to *key* at module level or as
    a class attribute — e.g. ``DATABASE_URL = "sqlite:///./app.db"`` or
    ``DATABASE_URL: str = "..."`` inside a ``Settings`` class.

    Using the AST instead of a regex makes this robust to reformatting,
    type annotations, and multi-line/implicitly-concatenated string values that
    a line-based regex would silently miss.

    Args:
        settings_file: Path to the settings module.
        key: The setting name to look up (e.g. ``"DATABASE_URL"``).

    Returns:
        The literal string value, or ``None`` if not found / not a plain string.
    """
    try:
        tree = ast.parse(settings_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None

    for node in ast.walk(tree):
        # Plain assignment:  DATABASE_URL = "..."
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        # Annotated assignment:  DATABASE_URL: str = "..."
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        else:
            continue

        for target in targets:
            if isinstance(target, ast.Name) and target.id == key:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
    return None


def _get_db_type_from_config() -> str:
    """Read db_type from .kaira.json or fallback to env URL inspection.

    Returns:
        Database type string, e.g. 'postgresql'.
    """
    try:
        from kaira.config import get_config

        cfg = get_config()
        return cfg.db_type
    except Exception:
        url = _get_database_url()
        for db in ("postgresql", "mysql", "mongodb", "sqlite"):
            if db in url.lower():
                return db
        return "unknown"


def _update_env_files(key: str, value: str) -> None:
    """Set a key=value pair in all .env* files in the current directory.

    Args:
        key: Environment variable name.
        value: Value to set (if already present — active or commented-out — the line is replaced).
    """
    env_files = list(Path.cwd().glob(".env*"))
    for env_file in env_files:
        if env_file.is_dir():
            continue
        try:
            content = env_file.read_text(encoding="utf-8")
            # Match both active (KEY=...) and commented-out (# KEY=...) forms
            pattern = rf"^#?\s*{key}=.*$"
            replacement = f"# {key}={value}\n# Uncomment and fill in your real credentials before running the app."
            if re.search(pattern, content, flags=re.MULTILINE):
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                content += f"\n# {key}={value}\n# Uncomment and fill in your real credentials before running the app.\n"
            env_file.write_text(content, encoding="utf-8")
        except OSError:
            pass


def _test_connection_real(db_type: str, raw_url: str) -> tuple[bool, str]:
    """Perform a real login and query connection check, returning (success, error_msg)."""
    if db_type == "sqlite":
        # SQLite is local; always succeeds if we can open the database file path
        return True, ""

    import asyncio

    async def check_conn():
        if db_type == "mongodb":
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(raw_url, serverSelectionTimeoutMS=2000)
            await client.admin.command("ping")
            return True, ""
        else:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text

            # Parse engine and test a simple query
            engine = create_async_engine(
                raw_url, connect_args={"timeout": 3} if db_type == "postgresql" else {}
            )
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            await engine.dispose()
            return True, ""

    try:
        # Run async check inside a synchronous wrapper
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success, msg = loop.run_until_complete(check_conn())
            return success, msg
        finally:
            loop.close()
    except Exception as exc:
        return False, str(exc)


def _set_env_active(key: str, value: str, files: list[Path]) -> None:
    """Set ``key=value`` as an **active** (uncommented) line in each env file.

    Unlike :func:`_update_env_files`, which comments values out for the user to
    fill in later, this writes a live value — used for Phase 6 settings
    (``DB_MODE``/``OFFLINE_DATABASE_URL``) and the provisioned ``DATABASE_URL``
    that must be readable by the running app immediately.

    Existing active or commented forms of the key are replaced in place; the
    surrounding file is otherwise left untouched (never truncated/overwritten).

    Args:
        key: Environment variable name.
        value: Value to write.
        files: Target env files (created if missing).
    """
    line = f"{key}={value}"
    pattern = rf"^#?\s*{re.escape(key)}=.*$"
    for env_file in files:
        try:
            content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
            if re.search(pattern, content, flags=re.MULTILINE):
                content = re.sub(pattern, line, content, flags=re.MULTILINE)
            else:
                if content and not content.endswith("\n"):
                    content += "\n"
                content += line + "\n"
            env_file.write_text(content, encoding="utf-8")
        except OSError:
            pass


def _get_db_type_from_url(url: str, default_type: str) -> str:
    """Extract database type dynamically from the connection URL protocol."""
    url_lower = url.lower()
    if "sqlite" in url_lower:
        return "sqlite"
    if "mongo" in url_lower:
        return "mongodb"
    if "postgres" in url_lower:
        return "postgresql"
    if "mysql" in url_lower:
        return "mysql"
    return default_type


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _password_prompt_factory(non_interactive: bool):
    """Return a ``prompt_password`` callback for the provisioner, or ``None``.

    The callback renders the explain-before-asking panel (host/user/db shown),
    routes masked input through :func:`kaira.core.prompts.secret`, and treats a
    blank submission as a graceful skip. Returns ``None`` in non-interactive
    contexts so the provisioner never blocks an automated run.
    """
    import sys

    if non_interactive or not sys.stdin.isatty():
        return None

    from kaira.core import prompts
    from kaira.core.theme import Theme, sym

    def _prompt(ctx) -> Optional[str]:  # type: ignore[no-untyped-def]
        lock = sym("LOCK")
        if ctx.last_error:
            console.print(
                f"  [{Theme.ERROR}]{sym('FAIL')} Authentication failed for user "
                f'"{ctx.user}" (attempt {ctx.attempt} of {ctx.max_attempts})[/{Theme.ERROR}]\n'
                f"     The password didn't match. Try again, or leave blank to\n"
                f"     skip and use offline SQLite."
            )
        else:
            console.print(
                Panel(
                    f"[bold]{lock} {ctx.engine.capitalize()} needs a password[/bold]\n\n"
                    f"Kaira detected a running {ctx.engine} server but it requires\n"
                    f'authentication. Enter the password for user "{ctx.user}"\n'
                    f'to create the "{ctx.db_name}" database.\n\n'
                    f"  Host:  {ctx.host}:{ctx.port}\n"
                    f"  User:  {ctx.user}\n"
                    f"  [dim](leave blank to skip and use offline SQLite instead)[/dim]",
                    border_style=Theme.BORDER_WARNING,
                )
            )
        try:
            value = prompts.secret("Password", flag="--skip")
        except typer.Exit:
            return None
        return value or None

    return _prompt


def _env_password(engine: str) -> Optional[str]:
    """Return a password already present in the environment, if any (§1.3)."""
    if engine == "postgresql":
        return os.environ.get("PGPASSWORD") or None
    if engine == "mysql":
        return os.environ.get("MYSQL_PWD") or None
    return None


def provision_and_persist(
    engine: str,
    project_name: str,
    cwd: Path,
    *,
    db_name: Optional[str] = None,
    skip: bool = False,
    profile: str = "solo",
    assume_yes: bool = False,
    non_interactive: bool = False,
) -> "object":
    """Provision the database and persist the result to ``.env*`` and ``.kaira.json``.

    Shared by ``kaira db create`` and ``kaira init``. Announces every step,
    masks the DSN everywhere, writes an entered password only to
    ``.env.development`` (git-ignored), and records the resolved mode.

    Args:
        engine: Database engine.
        project_name: Raw project name (used to derive the DB name).
        cwd: Project root where env/config files live.
        db_name: Explicit name override.
        skip: Scaffold the DSN only; do not touch the server.
        profile: ``solo`` | ``standard`` | ``scale`` (scale never auto-creates).
        assume_yes: Skip the create confirmation (``--yes``).
        non_interactive: Never prompt (CI / non-TTY).

    Returns:
        The :class:`~kaira.core.provisioner.ProvisionResult`.
    """
    from kaira.core import provisioner
    from kaira.core.theme import Theme, sym

    # scale: never auto-create (§1.5). Force scaffold-only.
    effective_skip = skip or profile == "scale"

    def announce(msg: str) -> None:
        console.print(f"  [{Theme.PRIMARY}]{sym('BOLT')}[/{Theme.PRIMARY}] {msg}")

    confirm_create = None if (assume_yes or profile == "solo") else _confirm_create_factory()

    result = provisioner.provision_database(
        engine,
        project_name,
        db_name=db_name,
        skip=effective_skip,
        env_password=_env_password(engine),
        prompt_password=_password_prompt_factory(non_interactive),
        confirm_create=confirm_create,
        announce=announce,
    )

    # ── Report outcome ───────────────────────────────────────────────────────
    if result.offline:
        console.print(f"  [{Theme.WARNING}]{sym('WARN')} {result.message}[/{Theme.WARNING}]")
        console.print(
            f"  [{Theme.MUTED}]→ start {engine} later and run: kaira db create[/{Theme.MUTED}]"
        )
    elif result.manual_sql:
        console.print(
            Panel(
                f"[{Theme.WARNING}]{sym('WARN')} cannot create database (insufficient privileges)\n"
                f"    run this once as a superuser, then re-run `kaira db create`:\n\n"
                f"    {result.manual_sql}[/{Theme.WARNING}]",
                border_style=Theme.BORDER_WARNING,
            )
        )
    else:
        console.print(f"  [{Theme.SUCCESS}]{sym('OK')} {result.message}[/{Theme.SUCCESS}]")

    _persist_provision(cwd, engine, result)
    return result


def _confirm_create_factory():
    """Return a confirm callback for the create prompt (standard profile)."""
    from kaira.core import prompts

    def _confirm(name: str) -> bool:
        try:
            return prompts.confirm(f'database "{name}" does not exist — create it?', default=True)
        except typer.Exit:
            return False

    return _confirm


def _persist_provision(cwd: Path, engine: str, result: "object") -> None:
    """Write DSN/mode to env files and update ``.kaira.json`` after provisioning."""
    from kaira.core.provisioner import ProvisionResult, offline_store_url
    from kaira.core.theme import Theme, sym

    assert isinstance(result, ProvisionResult)
    env_file = cwd / ".env"
    env_dev = cwd / ".env.development"
    # Offline store must match the data-model family (SQLite for relational,
    # local MongoDB for Mongo — never blanket SQLite; Phase 6 §3.3).
    offline_url = offline_store_url(engine, result.db_name)

    # Live mode + offline URL belong in .env (no secrets there).
    _set_env_active("DB_MODE", result.mode, [env_file])
    _set_env_active("OFFLINE_DATABASE_URL", offline_url, [env_file])
    _set_env_active("FALLBACK_MODE", "off", [env_file])

    # The provisioned DSN (may contain a password) goes ONLY to .env.development.
    if not result.offline:
        _set_env_active("DATABASE_URL", result.dsn, [env_dev])
        if result.password_entered:
            console.print(
                f"  [{Theme.SUCCESS}]{sym('OK')} credentials saved to "
                f".env.development (git-ignored)[/{Theme.SUCCESS}]"
            )
    else:
        # Offline: run against the fallback store explicitly (never silently).
        _set_env_active("DATABASE_URL", offline_url, [env_dev])

    # Record in .kaira.json in *this* project's directory (not necessarily cwd).
    try:
        import json

        from kaira.config import KairaConfig

        config_path = cwd / ".kaira.json"
        data: dict = {}
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        cfg = KairaConfig.from_dict(data) if data else KairaConfig()
        cfg.db_name = result.db_name
        cfg.db_provisioned = not result.offline
        cfg.db_mode = result.mode
        config_path.write_text(
            json.dumps(cfg.to_dict(), indent=2), encoding="utf-8"
        )
    except Exception:
        pass


@app.command("create")
def db_create(
    name: Annotated[
        Optional[str],
        typer.Option("--name", help="Override the derived database name."),
    ] = None,
    skip: Annotated[
        bool,
        typer.Option("--skip", help="Scaffold the DSN only; don't touch the server."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the create confirmation."),
    ] = False,
) -> None:
    """Provision (create) the database for the current project.

    Detects a local server, creates a database named after the project, wires
    the DSN into ``.env.development``, and falls back to offline SQLite if no
    server is reachable — so this command always completes.

    Examples
    --------
    kaira db create
    kaira db create --name customdb
    kaira db create --skip
    """
    engine = _get_db_type_from_config()
    if engine in ("unknown", ""):
        console.print(
            Panel(
                "[red]No database type configured. Run this inside a Kaira project "
                "or set db_type in .kaira.json.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    try:
        from kaira.config import get_config

        project_name = get_config().db_name or Path.cwd().name
    except Exception:
        project_name = Path.cwd().name

    provision_and_persist(
        engine,
        name or project_name,
        Path.cwd(),
        db_name=name,
        skip=skip,
        assume_yes=yes,
    )


@app.command("connect")
def db_connect() -> None:
    """Test the database connection using the configured DATABASE_URL."""
    raw_url = _get_database_url()
    if not raw_url:
        console.print(
            Panel(
                "[red]DATABASE_URL not set.\nAdd it to your .env file or export it.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    masked = mask_credentials(raw_url)
    config_db_type = _get_db_type_from_config()
    db_type = _get_db_type_from_url(raw_url, config_db_type)

    console.print(
        f"[cyan]Testing database connection (real login check):[/cyan] {masked}"
    )

    success, err_msg = _test_connection_real(db_type, raw_url)
    if success:
        console.print(
            Panel(
                f"[green]✅ Connected successfully to {db_type} database![/green]",
                border_style="green",
            )
        )
    else:
        err_msg_clean = mask_credentials(err_msg)
        console.print(
            Panel(
                f"[red]❌ Connection failed: {err_msg_clean}\n\nURL: {masked}[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command("status")
def db_status() -> None:
    """Show database configuration and connection status."""
    config_db_type = _get_db_type_from_config()
    raw_url = _get_database_url()
    masked = mask_credentials(raw_url) if raw_url else "[dim]DATABASE_URL not set[/dim]"
    db_type = (
        _get_db_type_from_url(raw_url, config_db_type) if raw_url else config_db_type
    )

    table = Table(title="⚡ Kaira — DB Status", border_style="cyan")
    table.add_column("Property", style="dim")
    table.add_column("Value")
    table.add_row("DB Type", f"[bold]{db_type}[/bold]")
    table.add_row("URL", masked)

    if not raw_url:
        table.add_row("Connection", "[dim]Not configured[/dim]")
    else:
        success, _ = _test_connection_real(db_type, raw_url)
        if success:
            table.add_row("Connection", "[green]✅ Reachable (Login OK)[/green]")
        else:
            table.add_row("Connection", "[red]❌ Connection Failed[/red]")

    console.print(table)


@app.command("info")
def db_info() -> None:
    """Display information about tables/collections in the database."""
    raw_url = _get_database_url()
    if not raw_url:
        console.print(
            Panel(
                "[red]DATABASE_URL not set.\nAdd it to your .env file or export it.[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    config_db_type = _get_db_type_from_config()
    db_type = _get_db_type_from_url(raw_url, config_db_type)
    masked = mask_credentials(raw_url)
    console.print(f"[cyan]Retrieving database information from:[/cyan] {masked}\n")

    import asyncio

    async def fetch_info():
        if db_type == "mongodb":
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(raw_url, serverSelectionTimeoutMS=3000)
            db_name = raw_url.split("/")[-1]
            if "?" in db_name:
                db_name = db_name.split("?")[0]
            if not db_name:
                db_name = "admin"
            db = client[db_name]
            collections = await db.list_collection_names()
            data = []
            for coll_name in collections:
                count = await db[coll_name].count_documents({})
                data.append({"name": coll_name, "count": count})
            return db_name, data
        else:
            from sqlalchemy.ext.asyncio import create_async_engine

            engine = create_async_engine(raw_url)

            def get_inspector_info(sync_conn):
                from sqlalchemy import inspect, text

                inspector = inspect(sync_conn)
                table_names = inspector.get_table_names()
                tables_data = []
                for t_name in table_names:
                    columns = inspector.get_columns(t_name)
                    try:
                        row_count = sync_conn.execute(text(f"SELECT COUNT(*) FROM {t_name}")).scalar()
                    except Exception:
                        row_count = 0
                    tables_data.append({"name": t_name, "columns": len(columns), "rows": row_count})
                return tables_data

            async with engine.connect() as conn:
                tables = await conn.run_sync(get_inspector_info)
            await engine.dispose()

            db_name = raw_url.split("/")[-1]
            if "?" in db_name:
                db_name = db_name.split("?")[0]
            if not db_name:
                db_name = "local"
            return db_name, tables

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            db_name, items = loop.run_until_complete(fetch_info())
        finally:
            loop.close()
    except Exception as exc:
        console.print(
            Panel(
                f"[red]❌ Failed to retrieve database info: {mask_credentials(str(exc))}[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    table = Table(
        title=f"⚡ Kaira — Database Info ({db_type.upper()}: [cyan]{db_name}[/cyan])",
        border_style="cyan",
    )

    if db_type == "mongodb":
        table.add_column("Collection", style="bold cyan")
        table.add_column("Documents", justify="right", style="green")
        for item in items:
            table.add_row(item["name"], str(item["count"]))
        item_label = "collection"
    else:
        table.add_column("Table", style="bold cyan")
        table.add_column("Columns", justify="right", style="yellow")
        table.add_column("Rows", justify="right", style="green")
        for item in items:
            table.add_row(item["name"], str(item["columns"]), str(item["rows"]))
        item_label = "table"

    console.print(table)
    console.print(f"\n[dim]Total: {len(items)} {item_label}(s) found.[/dim]")


@app.command("reset")
def db_reset(
    force: Annotated[
        bool, typer.Option("--force", help="Skip typed confirmation (CI mode)")
    ] = False,
) -> None:
    """Drop and recreate the database (DESTRUCTIVE). Blocked in production.

    Args:
        force: Bypass typed confirmation for CI use.
    """
    db_type = _get_db_type_from_config()
    if not typed_confirmation(
        "reset",
        "This will DROP and RECREATE the database. All data will be lost.",
        force=force,
    ):
        return

    if db_type == "mongodb":
        console.print(
            "[yellow]MongoDB reset: drop and recreate the database manually via mongosh.[/yellow]"
        )
        return

    console.print(
        Panel(
            "[yellow]⚠️  Database reset requires running Alembic downgrade + upgrade.\n"
            "Run:\n"
            "  alembic downgrade base\n"
            "  alembic upgrade head[/yellow]",
            border_style="yellow",
        )
    )


@app.command("shell")
def db_shell() -> None:
    """Open an interactive database shell (psql / mysql / mongosh / sqlite3)."""
    db_type = _get_db_type_from_config()
    client = _DB_CLIENTS.get(db_type)

    if not client:
        console.print(f"[red]Unknown database type: {db_type}[/red]")
        raise typer.Exit(1)

    if not shutil.which(client):
        console.print(
            Panel(
                f"[yellow]'{client}' not found in PATH.\n"
                f"Install the {db_type} client to use this command.[/yellow]",
                border_style="yellow",
            )
        )
        raise typer.Exit(1)

    raw_url = _get_database_url()
    cmd = [client]
    if raw_url and db_type != "sqlite":
        cmd.append(mask_credentials(raw_url).replace("***:***@", ":@"))  # best-effort
        # Actually pass original URL (not masked) to the real client
        cmd = [client, raw_url] if db_type != "mongodb" else [client, raw_url]

    console.print(f"[cyan]Launching {client}...[/cyan]")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


@app.command("backup")
def db_backup(
    output: Annotated[
        Optional[str],
        typer.Option("--output", "-o", help="Output directory for backup file"),
    ] = None,
) -> None:
    """Backup the database to a dump file.

    Args:
        output: Directory to write the backup to (default: current directory).
    """
    import datetime

    db_type = _get_db_type_from_config()
    out_dir = Path(output) if output else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"backup_{db_type}_{timestamp}.dump"

    tool_map = {"postgresql": "pg_dump", "mysql": "mysqldump"}
    tool = tool_map.get(db_type)

    if db_type == "sqlite":
        raw_url = _get_database_url()
        db_path_match = re.search(r"sqlite(?:\+aiosqlite)?:///(.+)", raw_url or "")
        db_path = db_path_match.group(1) if db_path_match else "./app.db"
        import shutil as _sh

        _sh.copy2(db_path, str(out_file).replace(".dump", ".db"))
        console.print(
            f"[green]✅ SQLite backup saved: {out_file.with_suffix('.db')}[/green]"
        )
        return

    if db_type == "mongodb":
        if not shutil.which("mongodump"):
            console.print(
                "[yellow]mongodump not found. Install MongoDB Database Tools.[/yellow]"
            )
            raise typer.Exit(1)
        subprocess.run(["mongodump", "--out", str(out_dir / f"backup_{timestamp}")])
        console.print(
            f"[green]✅ MongoDB backup saved: {out_dir / f'backup_{timestamp}'}[/green]"
        )
        return

    if not tool or not shutil.which(tool):
        console.print(
            f"[yellow]{tool or 'backup tool'} not found. Install the {db_type} client tools.[/yellow]"
        )
        raise typer.Exit(1)

    raw_url = _get_database_url()
    subprocess.run([tool, raw_url, "-f", str(out_file)])
    console.print(f"[green]✅ Backup saved: {out_file}[/green]")


@app.command("restore")
def db_restore(
    file: Annotated[str, typer.Argument(help="Path to backup file to restore")],
    force: Annotated[
        bool, typer.Option("--force", help="Skip typed confirmation")
    ] = False,
) -> None:
    """Restore the database from a backup file. Blocked in production.

    Args:
        file: Path to the backup dump file.
        force: Bypass typed confirmation for CI use.
    """
    if not typed_confirmation(
        "restore",
        f"This will RESTORE the database from '{file}'. Current data will be overwritten.",
        force=force,
    ):
        return

    backup_path = Path(file)
    if not backup_path.exists():
        console.print(f"[red]Backup file not found: {file}[/red]")
        raise typer.Exit(1)

    db_type = _get_db_type_from_config()
    tool_map = {"postgresql": "psql", "mysql": "mysql"}
    tool = tool_map.get(db_type)

    if db_type == "sqlite":
        raw_url = _get_database_url()
        db_path_match = re.search(r"sqlite(?:\+aiosqlite)?:///(.+)", raw_url or "")
        db_path = db_path_match.group(1) if db_path_match else "./app.db"
        import shutil as _sh

        _sh.copy2(file, db_path)
        console.print(f"[green]✅ SQLite restored from {file}[/green]")
        return

    if not tool or not shutil.which(tool):
        console.print(f"[yellow]{tool or 'restore tool'} not found.[/yellow]")
        raise typer.Exit(1)

    raw_url = _get_database_url()
    subprocess.run([tool, raw_url, "-f", file])
    console.print(f"[green]✅ Database restored from {file}[/green]")


@app.command("switch")
def db_switch(
    db_type: Annotated[
        str,
        typer.Argument(
            help="New database type: postgresql | mysql | mongodb | sqlite | supabase | atlas | firebase"
        ),
    ],
) -> None:
    """Switch the project's database type. Updates .kaira.json and .env files.

    Recognises cloud provider names (supabase, atlas, firebase) and routes
    them to ``kaira cloud connect`` automatically.

    Args:
        db_type: Target database type or cloud provider name.
    """
    # Phase 5 — route cloud provider names to cloud connect wizard
    _CLOUD_PROVIDERS = {"supabase", "atlas", "firebase"}
    if db_type.lower() in _CLOUD_PROVIDERS:
        console.print(
            f"[bold cyan]ℹ[/bold cyan]  '{db_type}' is a cloud provider — launching "
            f"[bold cyan]kaira cloud connect --provider {db_type}[/bold cyan]..."
        )
        from kaira.commands.cloud_cmd import cloud_connect

        cloud_connect(provider=db_type.lower())
        return

    valid = {"postgresql", "mysql", "mongodb", "sqlite"}
    if db_type not in valid:
        from kaira.commands.smart_errors import smart_error

        smart_error(
            context=f"Unknown database type: {db_type}",
            typed=db_type,
            candidates=list(valid | _CLOUD_PROVIDERS),
            guide_topic="db",
        )

    try:
        from kaira.config import get_config, save_config

        cfg = get_config()
        old_type = cfg.db_type
    except Exception:
        old_type = "unknown"

    # Warn on relational ↔ MongoDB switch
    old_is_relational = old_type in _RELATIONAL
    new_is_relational = db_type in _RELATIONAL
    if old_is_relational != new_is_relational:
        console.print(
            Panel(
                f"[yellow]⚠️  Switching from [bold]{old_type}[/bold] to [bold]{db_type}[/bold] "
                f"is a BREAKING change.\n"
                f"Generated model and repository files will need to be regenerated.\n"
                f"Run [bold]kaira generate model <Name>[/bold] after switching.[/yellow]",
                border_style="yellow",
            )
        )

    # Update .kaira.json
    try:
        from kaira.config import get_config, save_config

        cfg = get_config()
        cfg.db_type = db_type
        save_config(cfg)
        console.print(f"[green]✅ .kaira.json updated: db_type = {db_type}[/green]")
    except Exception as exc:
        console.print(f"[yellow]Could not update .kaira.json: {exc}[/yellow]")

    # Update DATABASE_URL placeholder in .env files
    url_map = {
        "postgresql": "postgresql+asyncpg://user:password@localhost/mydb",
        "mysql": "mysql+aiomysql://user:password@localhost/mydb",
        "mongodb": "mongodb://localhost:27017/mydb",
        "sqlite": "sqlite+aiosqlite:///./app.db",
    }
    _update_env_files("DATABASE_URL", url_map[db_type])
    console.print("[green]✅ DATABASE_URL placeholder updated in .env files[/green]")

    # Install driver
    drivers = _DB_DRIVERS.get(db_type, [])
    if drivers:
        from kaira.commands.project import install_packages

        install_packages(drivers)

    console.print(
        Panel(
            f"[green]✅ Switched to [bold]{db_type}[/bold].\n"
            f"Update DATABASE_URL in your .env files with real credentials.",
            border_style="green",
        )
    )


@app.command("benchmark")
def db_benchmark() -> None:
    """Run a basic connection and query timing benchmark."""
    import time

    db_type = _get_db_type_from_config()
    raw_url = _get_database_url()
    masked = mask_credentials(raw_url) if raw_url else "[dim]not set[/dim]"

    console.print(f"[cyan]Benchmarking {db_type} connection...[/cyan]")
    console.print(f"[dim]URL: {masked}[/dim]\n")

    if db_type == "sqlite":
        # Simple file I/O benchmark
        start = time.perf_counter()
        import sqlite3 as _sqlite3

        raw_path = re.search(r"sqlite(?:\+aiosqlite)?:///(.+)", raw_url or "")
        db_path = raw_path.group(1) if raw_path else ":memory:"
        conn = _sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        elapsed = (time.perf_counter() - start) * 1000
        console.print(f"[green]✅ SQLite query: {elapsed:.2f}ms[/green]")
        return

    port_map = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
    port = port_map.get(db_type, 0)
    host = "localhost"
    m = re.search(r"@([^:/]+)[:/]", raw_url or "")
    if m:
        host = m.group(1)

    if not port:
        console.print("[yellow]Cannot benchmark unknown database type.[/yellow]")
        return

    import socket

    times = []
    for i in range(5):
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=2.0):
                pass
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        except Exception:
            console.print(f"[red]Connection {i + 1}: failed[/red]")

    if times:
        avg = sum(times) / len(times)
        mn = min(times)
        mx = max(times)
        table = Table(title=f"Benchmark Results — {db_type}", border_style="cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value")
        table.add_row("Samples", str(len(times)))
        table.add_row("Avg", f"{avg:.2f}ms")
        table.add_row("Min", f"{mn:.2f}ms")
        table.add_row("Max", f"{mx:.2f}ms")
        console.print(table)
    else:
        console.print("[red]❌ All connections failed.[/red]")
        raise typer.Exit(1)
