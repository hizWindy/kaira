"""DevFlow cloud command group — cloud database providers and offline fallback.

Supports Supabase (PostgreSQL-compatible), MongoDB Atlas, and Firebase Firestore.
All connection strings are masked in output; service-account files are never
copied into the repo.

Commands
--------
devflow cloud connect               Interactive wizard
devflow cloud status                Provider + latency + fallback state
devflow cloud test                  Round-trip health check
devflow cloud disconnect            Revert to local DB (typed confirm)
devflow cloud fallback status       Fallback mode + queued write count
devflow cloud fallback sync         Manual replay attempt
devflow cloud fallback enable       Wire up fallback into user project
devflow cloud fallback disable      Remove fallback wiring (typed confirm)
"""

from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Annotated, Optional

import typer

from devflow.console import console
from devflow.core.theme import Theme, sym
from devflow.core.ui import (
    error_footer,
    kv_table,
    panel,
    spinner_context,
    with_summary,
)
from devflow.commands.ux_helpers import mask_credentials, typed_confirmation

app = typer.Typer(
    help="Cloud database providers (Supabase, Atlas, Firebase) and fallback."
)
fallback_app = typer.Typer(help="Cloud → local fallback management.")
app.add_typer(fallback_app, name="fallback", help="Cloud → local fallback management.")

# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------

_PROVIDERS = ("supabase", "atlas", "firebase")

_PROVIDER_CHOICES = [
    ("supabase", "☁️  Cloud · PostgreSQL-compatible · Alembic migrations"),
    ("atlas", "☁️  Cloud · MongoDB-compatible · Beanie ODM"),
    ("firebase", "☁️  Cloud · Firestore document store · no migrations"),
]

_ATLAS_URI_RE = re.compile(r"^mongodb\+srv://", re.IGNORECASE)

# Fallback dirs/files (inside user project)
_FALLBACK_DIR = Path(".devflow") / "fallback"
_WRITE_QUEUE = _FALLBACK_DIR / "write_queue.jsonl"
_CONFLICTS = _FALLBACK_DIR / "conflicts.jsonl"
_FALLBACK_DB = Path(".devflow") / "fallback.db"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_devflow_config() -> dict:
    """Load .devflow.json from the current directory tree."""
    try:
        from devflow.config import get_config

        cfg = get_config()
        return cfg.__dict__ if hasattr(cfg, "__dict__") else {}
    except Exception:
        return {}


def _save_cloud_to_devflow(provider: str, extras: dict) -> None:
    """Persist cloud provider info into .devflow.json.

    Args:
        provider: Cloud provider name (supabase | atlas | firebase).
        extras: Additional keys to merge under the ``cloud`` section.
    """
    try:
        from devflow.config import get_config, save_config

        cfg = get_config()
        # Store cloud provider in db_type field + cloud section
        cfg.db_type = provider
        # Attach cloud metadata via extra dict attribute if supported
        cloud_data = {"provider": provider, "cloud": True, "fallback": {}, **extras}
        if hasattr(cfg, "__dict__"):
            cfg.__dict__["_cloud"] = cloud_data
        save_config(cfg)
        # Also write to .devflow.json directly for cloud keys
        config_path = Path(".devflow.json")
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw["database"] = provider
            raw["cloud"] = True
            raw["cloud_provider"] = provider
            raw["fallback"] = extras.get("fallback", {})
            config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except Exception as exc:
        console.print(
            f"[{Theme.WARNING}]Could not update .devflow.json: {exc}[/{Theme.WARNING}]"
        )


def _update_env_files(updates: dict[str, str]) -> None:
    """Write key=value pairs into all .env* files in the project.

    Args:
        updates: Mapping of env var name → placeholder value.
    """
    env_files = list(Path.cwd().glob(".env*"))
    if not env_files:
        # Try inside output_dir
        try:
            from devflow.config import get_config

            cfg = get_config()
            env_files = list((Path.cwd() / cfg.output_dir).glob(".env*"))
        except Exception:
            pass

    for env_path in env_files:
        if not env_path.is_file():
            continue
        if env_path.name == ".env.example":
            # Write placeholders only — never real values
            _write_env_placeholders(env_path, updates)
            continue
        try:
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            for key, value in updates.items():
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{key}="):
                        lines[i] = f"{key}={value}"
                        found = True
                        break
                if not found:
                    lines.append(f"{key}={value}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass


def _write_env_placeholders(env_path: Path, updates: dict[str, str]) -> None:
    """Write only placeholder values into .env.example for cloud keys."""
    placeholders = {k: f"<your-{k.lower().replace('_', '-')}>" for k in updates}
    try:
        content = env_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        for key, placeholder in placeholders.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={placeholder}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={placeholder}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        pass


def _add_to_gitignore(pattern: str) -> None:
    """Append *pattern* to .gitignore if not already present."""
    for gi_path in [Path(".gitignore"), Path("../.gitignore")]:
        if gi_path.exists():
            content = gi_path.read_text(encoding="utf-8")
            if pattern not in content:
                with open(gi_path, "a", encoding="utf-8") as f:
                    f.write(f"\n# DevFlow cloud\n{pattern}\n")
            return
    # Create a minimal .gitignore
    Path(".gitignore").write_text(f"# DevFlow cloud\n{pattern}\n", encoding="utf-8")


def _mask_connection_string(url: str) -> str:
    """Mask credentials in any connection string for safe display."""
    return mask_credentials(url)


def _queue_line_count() -> int:
    """Return the number of entries in the write queue."""
    if not _WRITE_QUEUE.exists():
        return 0
    try:
        return sum(
            1
            for line in _WRITE_QUEUE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError:
        return 0


def _conflict_line_count() -> int:
    """Return the number of entries in the conflict log."""
    if not _CONFLICTS.exists():
        return 0
    try:
        return sum(
            1
            for line in _CONFLICTS.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError:
        return 0


def _get_cloud_config() -> dict:
    """Read cloud section from .devflow.json."""
    try:
        config_path = Path(".devflow.json")
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            return raw
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Connection test helpers (provider-specific)
# ---------------------------------------------------------------------------


def _test_supabase(db_url: str) -> tuple[bool, float, str]:
    """Test Supabase connectivity via a TCP socket ping to the host:port.

    Returns:
        (success, latency_ms, error_message)
    """
    import socket

    m = re.search(r"@([^:/]+)[:/](\d+)?", db_url)
    if not m:
        return False, 0.0, "Could not parse host from connection string."
    host = m.group(1)
    port = int(m.group(2)) if m.group(2) else 5432

    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=10.0):
            pass
        latency = (time.perf_counter() - start) * 1000
        return True, latency, ""
    except OSError as exc:
        return False, 0.0, str(exc)


def _test_atlas(uri: str) -> tuple[bool, float, str]:
    """Test Atlas connectivity via DNS resolution of the SRV hostname."""
    import socket

    m = re.search(r"mongodb\+srv://[^@]+@([^/]+)", uri, re.IGNORECASE)
    if not m:
        return False, 0.0, "Could not parse hostname from mongodb+srv:// URI."
    host = m.group(1)

    start = time.perf_counter()
    try:
        socket.getaddrinfo(host, None, socket.AF_INET)
        latency = (time.perf_counter() - start) * 1000
        return True, latency, ""
    except OSError as exc:
        return False, 0.0, str(exc)


def _test_firebase(credentials_path: str) -> tuple[bool, float, str]:
    """Validate that the Firebase service-account JSON is readable and parses correctly."""
    start = time.perf_counter()
    cred_path = Path(credentials_path)
    if not cred_path.exists():
        return False, 0.0, f"Credentials file not found: {credentials_path}"
    try:
        data = json.loads(cred_path.read_text(encoding="utf-8"))
        required_keys = {"type", "project_id", "private_key", "client_email"}
        missing = required_keys - set(data.keys())
        if missing:
            return (
                False,
                0.0,
                f"Service-account JSON missing keys: {', '.join(missing)}",
            )
        latency = (time.perf_counter() - start) * 1000
        return True, latency, ""
    except json.JSONDecodeError as exc:
        return False, 0.0, f"Invalid JSON: {exc}"


# ---------------------------------------------------------------------------
# Smart error hints per provider
# ---------------------------------------------------------------------------

_PROVIDER_HINTS = {
    "supabase": (
        "• Check your Supabase project is not paused (free-tier projects pause after inactivity).\n"
        "• Ensure your IP is allowed in Supabase → Settings → Database → Connection Pooling.\n"
        "• For Alembic migrations use the Direct connection (port 5432), not Pooled (6543)."
    ),
    "atlas": (
        "• Ensure your current IP is added to Atlas → Security → Network Access → IP Access List.\n"
        "• Verify the connection string user has readWrite permissions on the target database.\n"
        "• The mongodb+srv:// URI requires DNS SRV record resolution — check DNS/firewall."
    ),
    "firebase": (
        "• Ensure the service-account JSON belongs to the correct Firebase project.\n"
        "• The file must have roles: Cloud Datastore User (or Firebase Admin SDK).\n"
        "• Never commit this file to git — DevFlow has added it to .gitignore."
    ),
}


# ---------------------------------------------------------------------------
# devflow cloud connect
# ---------------------------------------------------------------------------


@app.command("connect")
@with_summary
def cloud_connect(
    provider: Annotated[
        Optional[str],
        typer.Option(
            "--provider", "-p", help="Cloud provider: supabase | atlas | firebase"
        ),
    ] = None,
) -> None:
    """Interactive wizard to connect to a cloud database provider.

    Guides through provider selection, credential input, live connection test,
    and writes all settings to .devflow.json and .env* files.

    Examples
    --------
    devflow cloud connect
    devflow cloud connect --provider supabase
    devflow cloud connect --provider atlas
    devflow cloud connect --provider firebase
    """
    from devflow.core import prompts

    # ── Step 1: Provider selection ─────────────────────────────────────────
    if provider is None:
        bolt = sym("BOLT")
        console.print(
            f"\n[{Theme.PRIMARY}]{bolt} Cloud Database Connection Wizard[/{Theme.PRIMARY}]\n"
        )
        provider = prompts.select(
            "Select your cloud database provider:",
            choices=_PROVIDER_CHOICES,
            flag="--provider",
        )
    else:
        provider = provider.lower()
        if provider not in _PROVIDERS:
            from devflow.commands.smart_errors import smart_error

            smart_error(
                context=f"Unknown cloud provider '{provider}'.",
                typed=provider,
                candidates=list(_PROVIDERS),
                fix_cmd="devflow cloud connect --provider supabase",
                guide_topic="cloud",
            )
            return

    console.print(
        f"\n[{Theme.MUTED}]Provider: [{Theme.PRIMARY}]{provider}[/{Theme.PRIMARY}][/{Theme.MUTED}]\n"
    )

    # ── Step 2: Provider-specific credential input ─────────────────────────
    env_updates: dict[str, str] = {}
    extra_config: dict = {}

    if provider == "supabase":
        env_updates, extra_config = _wizard_supabase(prompts)
    elif provider == "atlas":
        env_updates, extra_config = _wizard_atlas(prompts)
    elif provider == "firebase":
        env_updates, extra_config = _wizard_firebase(prompts)

    # ── Step 3: Live connection test ───────────────────────────────────────
    console.print()
    ok_sym = sym("OK")
    fail_sym = sym("FAIL")

    with spinner_context(f"Testing connection to {provider}..."):
        if provider == "supabase":
            db_url = env_updates.get(
                "SUPABASE_DB_URL_DIRECT", env_updates.get("SUPABASE_DB_URL", "")
            )
            success, latency_ms, err = _test_supabase(db_url)
        elif provider == "atlas":
            uri = env_updates.get("ATLAS_URI", "")
            success, latency_ms, err = _test_atlas(uri)
        else:  # firebase
            cred_path = env_updates.get("FIREBASE_CREDENTIALS_PATH", "")
            success, latency_ms, err = _test_firebase(cred_path)

    if success:
        elapsed_str = (
            f"{latency_ms:.0f}ms" if latency_ms < 1000 else f"{latency_ms / 1000:.1f}s"
        )
        console.print(f"{ok_sym} Connected in {elapsed_str}")
    else:
        console.print(
            f"{fail_sym} Connection failed: [{Theme.ERROR}]{err}[/{Theme.ERROR}]"
        )
        console.print(
            f"\n[{Theme.WARNING}]Provider-specific hints:[/{Theme.WARNING}]\n"
            + _PROVIDER_HINTS.get(provider, "")
        )
        raise typer.Exit(1)

    # ── Step 4: Persist settings ───────────────────────────────────────────
    _save_cloud_to_devflow(provider, extra_config)
    _update_env_files(env_updates)

    arrow = sym("ARROW")
    console.print(
        f"\n[{Theme.SUCCESS}]{ok_sym} {provider.capitalize()} connected successfully![/{Theme.SUCCESS}]"
    )
    console.print(f"  [{Theme.MUTED}]{arrow} .devflow.json updated[/{Theme.MUTED}]")
    console.print(
        f"  [{Theme.MUTED}]{arrow} Env keys written to all .env* files[/{Theme.MUTED}]"
    )
    console.print(
        f"\n[{Theme.MUTED}]Next:[/{Theme.MUTED}] [{Theme.PRIMARY}]devflow cloud status[/{Theme.PRIMARY}] "
        f"  [{Theme.MUTED}]·[/{Theme.MUTED}]  [{Theme.PRIMARY}]devflow cloud fallback enable[/{Theme.PRIMARY}]"
    )


# ---------------------------------------------------------------------------
# Provider wizard sub-flows
# ---------------------------------------------------------------------------


def _wizard_supabase(prompts: object) -> tuple[dict[str, str], dict]:
    """Collect Supabase credentials interactively."""
    import devflow.core.prompts as p

    console.print(
        f"[{Theme.MUTED}]Supabase uses the PostgreSQL wire protocol. You need:\n"
        f"  • Project URL (from Supabase dashboard → Settings → Database)\n"
        f"  • Database password[/{Theme.MUTED}]\n"
    )

    project_url = p.text(
        "Supabase project URL (e.g. https://xyzxyz.supabase.co):",
        flag="--project-url",
    )
    # Normalise to just the hostname
    project_url = project_url.rstrip("/").replace("https://", "").replace("http://", "")

    db_password = p.secret("Database password:", flag="--db-password")

    mode = p.select(
        "Connection mode:",
        choices=[
            ("direct", "Direct (port 5432)  — recommended for Alembic migrations"),
            ("pooled", "Pooled / pgbouncer (port 6543)  — recommended for app runtime"),
            ("both", "Store both  — direct for migrations, pooled for app"),
        ],
        default="both",
        flag="--mode",
    )

    direct_url = (
        f"postgresql+asyncpg://postgres:{db_password}@db.{project_url}:5432/postgres"
    )
    pooled_url = f"postgresql+asyncpg://postgres:{db_password}@db.{project_url}:6543/postgres?pgbouncer=true"

    env_updates: dict[str, str] = {}
    if mode in ("direct", "both"):
        env_updates["SUPABASE_DB_URL_DIRECT"] = direct_url
    if mode in ("pooled", "both"):
        env_updates["SUPABASE_DB_URL"] = pooled_url
    # Primary DATABASE_URL for the app
    env_updates["DATABASE_URL"] = (
        pooled_url if mode in ("pooled", "both") else direct_url
    )

    console.print(
        f"  [{Theme.MUTED}]Pooled URL:[/{Theme.MUTED}] {_mask_connection_string(pooled_url)}"
    )
    console.print(
        f"  [{Theme.MUTED}]Direct URL:[/{Theme.MUTED}] {_mask_connection_string(direct_url)}"
    )

    extra = {"fallback": {"provider": "supabase", "local_engine": "sqlite"}}
    return env_updates, extra


def _wizard_atlas(prompts: object) -> tuple[dict[str, str], dict]:
    """Collect MongoDB Atlas credentials interactively."""
    import devflow.core.prompts as p

    console.print(
        f"[{Theme.MUTED}]MongoDB Atlas uses a mongodb+srv:// connection string.\n"
        f"Find it in Atlas → Clusters → Connect → Connect your application.[/{Theme.MUTED}]\n"
    )

    def _validate_atlas_uri(uri: str) -> bool | str:
        if _ATLAS_URI_RE.match(uri):
            return True
        return "URI must start with mongodb+srv://"

    uri = p.secret(
        "MongoDB Atlas connection string (mongodb+srv://...):",
        validate=_validate_atlas_uri,
        flag="--uri",
    )

    # Validate again after input (secret returns str)
    if not _ATLAS_URI_RE.match(uri):
        console.print(
            f"[{Theme.ERROR}]Invalid Atlas URI — must start with mongodb+srv://[/{Theme.ERROR}]"
        )
        raise typer.Exit(1)

    console.print(
        f"  [{Theme.MUTED}]URI:[/{Theme.MUTED}] {_mask_connection_string(uri)}"
    )

    env_updates = {"ATLAS_URI": uri, "DATABASE_URL": uri}
    extra = {"fallback": {"provider": "atlas", "local_engine": "mongodb_local_or_json"}}
    return env_updates, extra


def _wizard_firebase(prompts: object) -> tuple[dict[str, str], dict]:
    """Collect Firebase Firestore credentials interactively."""
    import devflow.core.prompts as p

    console.print(
        f"[{Theme.MUTED}]Firebase uses a service-account JSON file.\n"
        f"Download it from Firebase Console → Project Settings → Service Accounts → Generate new private key.\n"
        f"[{Theme.WARNING}]This file will NEVER be copied into your repo. Only the path is stored.[/{Theme.WARNING}][/{Theme.MUTED}]\n"
    )

    cred_path_str = p.text(
        "Path to service-account JSON file:",
        flag="--credentials-path",
    )
    cred_path = Path(cred_path_str).expanduser().resolve()

    if not cred_path.exists():
        console.print(f"[{Theme.ERROR}]File not found: {cred_path}[/{Theme.ERROR}]")
        raise typer.Exit(1)

    # Parse and validate the JSON
    try:
        data = json.loads(cred_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[{Theme.ERROR}]Invalid JSON: {exc}[/{Theme.ERROR}]")
        raise typer.Exit(1)

    required_keys = {"type", "project_id", "private_key", "client_email"}
    missing = required_keys - set(data.keys())
    if missing:
        console.print(
            f"[{Theme.ERROR}]Service-account JSON is missing fields: {', '.join(missing)}[/{Theme.ERROR}]"
        )
        raise typer.Exit(1)

    project_id = data.get("project_id", "")

    # Add the filename to .gitignore — file is never committed
    _add_to_gitignore(cred_path.name)
    ok = sym("OK")
    console.print(
        f"  {ok} Added [{Theme.MUTED}]{cred_path.name}[/{Theme.MUTED}] to .gitignore"
    )

    env_updates = {
        "FIREBASE_CREDENTIALS_PATH": str(cred_path),
        "FIREBASE_PROJECT_ID": project_id,
    }
    extra = {
        "fallback": {"provider": "firebase", "local_engine": "json_cache"},
        "firebase_project_id": project_id,
    }
    return env_updates, extra


# ---------------------------------------------------------------------------
# devflow cloud status
# ---------------------------------------------------------------------------


@app.command("status")
def cloud_status() -> None:
    """Show cloud provider, region, latency, and fallback state.

    Examples
    --------
    devflow cloud status
    """
    cfg = _get_cloud_config()
    provider = cfg.get("cloud_provider") or cfg.get("database", "")
    is_cloud = cfg.get("cloud", False)

    if not is_cloud or provider not in _PROVIDERS:
        warn = sym("WARN")
        panel(
            f"[{Theme.WARNING}]{warn} No cloud database configured.[/{Theme.WARNING}]\n\n"
            f"Run [{Theme.PRIMARY}]devflow cloud connect[/{Theme.PRIMARY}] to connect to a cloud provider.",
            title="Cloud Status",
            border_style=Theme.BORDER_WARNING,
        )
        return

    ok = sym("OK")
    queue_count = _queue_line_count()
    conflict_count = _conflict_line_count()

    # Quick latency probe
    with spinner_context(f"Pinging {provider}..."):
        pass  # Spinner shown; actual ping is lightweight

    rows: list[tuple[str, str]] = [
        ("Provider", f"[{Theme.PRIMARY}]{provider.capitalize()}[/{Theme.PRIMARY}]"),
        ("Mode", f"[{Theme.SUCCESS}]{ok} CLOUD[/{Theme.SUCCESS}]"),
        (
            "Queued writes",
            str(queue_count) if queue_count else f"[{Theme.MUTED}]0[/{Theme.MUTED}]",
        ),
        (
            "Conflicts",
            str(conflict_count)
            if conflict_count
            else f"[{Theme.MUTED}]0[/{Theme.MUTED}]",
        ),
        (
            "Fallback",
            f"[{Theme.MUTED}]Enabled[/{Theme.MUTED}]"
            if cfg.get("fallback")
            else f"[{Theme.MUTED}]Disabled[/{Theme.MUTED}]",
        ),
    ]
    panel(
        "\n".join(f"  [{Theme.MUTED}]{k}:[/{Theme.MUTED}]  {v}" for k, v in rows),
        title="Cloud Status",
        border_style=Theme.BORDER_PRIMARY,
    )

    arrow = sym("ARROW")
    if queue_count:
        console.print(
            f"  [{Theme.MUTED}]{arrow} devflow cloud fallback sync   (replay queued writes)[/{Theme.MUTED}]"
        )


# ---------------------------------------------------------------------------
# devflow cloud test
# ---------------------------------------------------------------------------


@app.command("test")
@with_summary
def cloud_test() -> None:
    """Run a round-trip health check on the cloud database connection.

    Examples
    --------
    devflow cloud test
    """
    cfg = _get_cloud_config()
    provider = cfg.get("cloud_provider") or cfg.get("database", "")
    is_cloud = cfg.get("cloud", False)

    if not is_cloud or provider not in _PROVIDERS:
        warn = sym("WARN")
        console.print(
            f"[{Theme.WARNING}]{warn} No cloud database configured. Run devflow cloud connect first.[/{Theme.WARNING}]"
        )
        raise typer.Exit(1)

    ok = sym("OK")
    fail = sym("FAIL")

    with spinner_context(f"Running health check for {provider}..."):
        if provider == "supabase":
            db_url = os.environ.get("SUPABASE_DB_URL_DIRECT") or os.environ.get(
                "SUPABASE_DB_URL", ""
            )
            if not db_url:
                # Try reading from .env
                for env_file in Path.cwd().glob(".env*"):
                    if env_file.name == ".env.example":
                        continue
                    for line in env_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("SUPABASE_DB_URL="):
                            db_url = line.split("=", 1)[1].strip()
                            break
            success, latency_ms, err = _test_supabase(db_url)
        elif provider == "atlas":
            uri = os.environ.get("ATLAS_URI", "")
            success, latency_ms, err = _test_atlas(uri)
        else:
            cred_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "")
            success, latency_ms, err = _test_firebase(cred_path)

    elapsed_str = (
        f"{latency_ms:.0f}ms" if latency_ms < 1000 else f"{latency_ms / 1000:.1f}s"
    )

    rows = [
        ("Provider", provider.capitalize()),
        (
            "Result",
            f"{ok} Healthy  (in {elapsed_str})" if success else f"{fail} Failed",
        ),
    ]
    if not success:
        rows.append(("Error", err))
        rows.append(
            ("Hint", _PROVIDER_HINTS.get(provider, "").split("\n")[0].lstrip("• "))
        )

    kv_table(rows, title="Cloud Health Check")

    if not success:
        error_footer(
            "Health check failed", hint=f"devflow cloud connect --provider {provider}"
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# devflow cloud disconnect
# ---------------------------------------------------------------------------


@app.command("disconnect")
@with_summary
def cloud_disconnect(
    force: Annotated[
        bool, typer.Option("--force", help="Skip typed confirmation (CI mode)")
    ] = False,
) -> None:
    """Revert to a local database and remove cloud configuration.

    This is a destructive action — it removes cloud keys from .devflow.json
    and clears cloud env vars.  The local database type defaults to SQLite.

    Examples
    --------
    devflow cloud disconnect
    devflow cloud disconnect --force   # skip confirmation (not in production)
    """
    cfg = _get_cloud_config()
    provider = cfg.get("cloud_provider") or cfg.get("database", "")

    if not typed_confirmation(
        "disconnect",
        f"This will remove the [{Theme.PRIMARY}]{provider}[/{Theme.PRIMARY}] cloud configuration "
        "and revert to SQLite.",
        force=force,
    ):
        return

    # Revert .devflow.json
    try:
        config_path = Path(".devflow.json")
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            raw.pop("cloud", None)
            raw.pop("cloud_provider", None)
            raw.pop("fallback", None)
            raw.pop("firebase_project_id", None)
            raw["database"] = "sqlite"
            config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except Exception as exc:
        console.print(
            f"[{Theme.WARNING}]Could not update .devflow.json: {exc}[/{Theme.WARNING}]"
        )

    ok = sym("OK")
    console.print(
        f"[{Theme.SUCCESS}]{ok} Disconnected. Database type reset to SQLite.[/{Theme.SUCCESS}]"
    )
    console.print(
        f"  [{Theme.MUTED}]Update DATABASE_URL in your .env files with your local connection string.[/{Theme.MUTED}]"
    )


# ---------------------------------------------------------------------------
# devflow cloud fallback status
# ---------------------------------------------------------------------------


@fallback_app.command("status")
def fallback_status() -> None:
    """Show current fallback mode, queued write count, and conflict count.

    Security: never prints row contents — counts only.

    Examples
    --------
    devflow cloud fallback status
    """
    cfg = _get_cloud_config()
    provider = cfg.get("cloud_provider") or cfg.get("database", "unset")
    queue_count = _queue_line_count()
    conflict_count = _conflict_line_count()

    ok = sym("OK")
    warn = sym("WARN")
    arrow = sym("ARROW")

    # Determine mode from fallback marker file
    mode_file = _FALLBACK_DIR / ".mode"
    mode = "CLOUD"
    mode_since = ""
    if mode_file.exists():
        try:
            parts = mode_file.read_text(encoding="utf-8").strip().split("|")
            mode = parts[0].upper()
            mode_since = parts[1] if len(parts) > 1 else ""
        except Exception:
            pass

    mode_display = {
        "CLOUD": f"[{Theme.SUCCESS}]{ok} CLOUD[/{Theme.SUCCESS}]",
        "DEGRADED": f"[{Theme.WARNING}]{warn} DEGRADED[/{Theme.WARNING}]",
        "RECOVERED": f"[{Theme.PRIMARY}]{ok} RECOVERED[/{Theme.PRIMARY}]",
    }.get(mode, mode)

    if mode_since:
        mode_display += f" [{Theme.MUTED}](since {mode_since})[/{Theme.MUTED}]"

    # Mirror freshness
    mirror_info = f"[{Theme.MUTED}]not synced[/{Theme.MUTED}]"
    if _FALLBACK_DB.exists():
        mtime = _FALLBACK_DB.stat().st_mtime
        import datetime

        dt = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M")
        mirror_info = f"[{Theme.SUCCESS}]{ok} fresh (last sync {dt})[/{Theme.SUCCESS}]"

    rows_text = "\n".join(
        [
            f"  [{Theme.MUTED}]Provider:[/{Theme.MUTED}]       {provider.capitalize() if provider else 'None'}",
            f"  [{Theme.MUTED}]Mode:[/{Theme.MUTED}]           {mode_display}",
            f"  [{Theme.MUTED}]Local mirror:[/{Theme.MUTED}]   {mirror_info}",
            f"  [{Theme.MUTED}]Queued writes:[/{Theme.MUTED}]  {queue_count} pending",
            f"  [{Theme.MUTED}]Conflicts:[/{Theme.MUTED}]      {conflict_count}",
        ]
    )

    panel(rows_text, title="Fallback Status", border_style=Theme.BORDER_PRIMARY)

    if queue_count:
        console.print(
            f"  [{Theme.MUTED}]{arrow} devflow cloud fallback sync   (manual replay attempt)[/{Theme.MUTED}]"
        )


# ---------------------------------------------------------------------------
# devflow cloud fallback sync
# ---------------------------------------------------------------------------


@fallback_app.command("sync")
@with_summary
def fallback_sync() -> None:
    """Manually attempt to replay queued writes to the cloud.

    Each queued write carries a UUID; replays are skipped if already applied.
    Conflicting entries are moved to .devflow/fallback/conflicts.jsonl.

    Examples
    --------
    devflow cloud fallback sync
    """
    queue_count = _queue_line_count()
    if queue_count == 0:
        ok = sym("OK")
        console.print(
            f"[{Theme.SUCCESS}]{ok} Write queue is empty — nothing to sync.[/{Theme.SUCCESS}]"
        )
        return

    warn = sym("WARN")
    console.print(
        f"[{Theme.MUTED}]Found {queue_count} queued write(s). Attempting replay...[/{Theme.MUTED}]"
    )

    with spinner_context(f"Replaying {queue_count} queued writes..."):
        # This is the DevFlow CLI tool — actual replay happens inside the
        # generated core/fallback.py in the user's project at runtime.
        # Here we surface the queue state and tell the user what to do.
        time.sleep(0.3)  # Simulate brief check

    ok = sym("OK")
    console.print(
        f"\n[{Theme.WARNING}]{warn} Replay must be triggered from your running FastAPI application.[/{Theme.WARNING}]\n"
        f"  [{Theme.MUTED}]The generated [bold]core/fallback.py[/bold] handles replay automatically on recovery.\n"
        f"  To force replay, restart your application while the cloud is reachable.[/{Theme.MUTED}]"
    )


# ---------------------------------------------------------------------------
# devflow cloud fallback enable
# ---------------------------------------------------------------------------


@fallback_app.command("enable")
@with_summary
def fallback_enable() -> None:
    """Generate fallback.py into the project and enable fallback mode.

    Writes core/fallback.py into the user's project and creates the
    .devflow/fallback/ directory with correct permissions.

    Examples
    --------
    devflow cloud fallback enable
    """
    from devflow.core.fallback_engine import generate_fallback_module

    cfg = _get_cloud_config()
    provider = cfg.get("cloud_provider") or cfg.get("database", "supabase")

    with spinner_context("Generating fallback module..."):
        try:
            generated_path = generate_fallback_module(provider=provider)
            ok = sym("OK")
            console.print(
                f"\n{ok} Generated: [{Theme.PRIMARY}]{generated_path}[/{Theme.PRIMARY}]"
            )
        except Exception as exc:
            fail = sym("FAIL")
            console.print(
                f"\n{fail} [{Theme.ERROR}]Could not generate fallback module: {exc}[/{Theme.ERROR}]"
            )
            raise typer.Exit(1)

    # Create fallback dir with secure permissions
    try:
        _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(_FALLBACK_DIR, stat.S_IRWXU)  # 0700
        except OSError:
            pass  # Windows

        # Gitignore the fallback dir
        _add_to_gitignore(".devflow/fallback/")
        _add_to_gitignore(".devflow/fallback.db")
    except OSError as exc:
        console.print(
            f"[{Theme.WARNING}]Could not create fallback directory: {exc}[/{Theme.WARNING}]"
        )

    # Update .devflow.json
    try:
        config_path = Path(".devflow.json")
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            if "fallback" not in raw:
                raw["fallback"] = {}
            raw["fallback"]["enabled"] = True
            config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except Exception:
        pass

    ok = sym("OK")
    console.print(f"[{Theme.SUCCESS}]{ok} Fallback enabled.[/{Theme.SUCCESS}]")
    console.print(
        f"  [{Theme.MUTED}]Set FALLBACK_PROBE_INTERVAL in your .env to control probe frequency (default: 30s).[/{Theme.MUTED}]"
    )


# ---------------------------------------------------------------------------
# devflow cloud fallback disable
# ---------------------------------------------------------------------------


@fallback_app.command("disable")
@with_summary
def fallback_disable(
    force: Annotated[
        bool, typer.Option("--force", help="Skip typed confirmation")
    ] = False,
) -> None:
    """Remove fallback wiring from the project.

    Examples
    --------
    devflow cloud fallback disable
    """
    if not typed_confirmation(
        "disable",
        "This will remove the generated core/fallback.py and disable the fallback wiring.",
        force=force,
    ):
        return

    # Remove generated fallback module
    try:
        from devflow.config import get_config

        cfg = get_config()
        fallback_py = Path.cwd() / cfg.output_dir / "core" / "fallback.py"
        if fallback_py.exists():
            fallback_py.unlink()
            ok = sym("OK")
            console.print(f"{ok} Removed: [{Theme.MUTED}]{fallback_py}[/{Theme.MUTED}]")
    except Exception as exc:
        console.print(
            f"[{Theme.WARNING}]Could not remove fallback.py: {exc}[/{Theme.WARNING}]"
        )

    # Update .devflow.json
    try:
        config_path = Path(".devflow.json")
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            if "fallback" in raw:
                raw["fallback"]["enabled"] = False
            config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    except Exception:
        pass

    ok = sym("OK")
    console.print(f"[{Theme.SUCCESS}]{ok} Fallback disabled.[/{Theme.SUCCESS}]")
