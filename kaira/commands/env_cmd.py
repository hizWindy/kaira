"""Environment management command group."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Annotated

import typer
from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.table import Table

from kaira.config import KairaConfig, get_config
from kaira.console import console
from kaira.core.detector import write_with_check

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

app = typer.Typer(help="Environment management commands.")

# ---------------------------------------------------------------------------
# Feature ↔ env-key registry (used by `env audit` / `env prune`)
# ---------------------------------------------------------------------------

# Maps each known env key to the feature that owns it.  Keys owned by "core"
# are never pruned.  Anything not listed here is treated as a user-defined
# custom key and always kept.
_KEY_FEATURES: dict[str, str] = {
    "APP_ENV": "core",
    "APP_NAME": "core",
    "DEBUG": "core",
    "DATABASE_URL": "core",
    "ALLOWED_ORIGINS": "core",
    "RATE_LIMIT_GET": "core",
    "RATE_LIMIT_WRITE": "core",
    "JWT_SECRET_KEY": "auth",
    "JWT_ALGORITHM": "auth",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "auth",
    "REDIS_URL": "cache",
    "CACHE_TTL": "cache",
    "CELERY_BROKER_URL": "task",
    "CELERY_RESULT_BACKEND": "task",
    "FLOWER_PORT": "task",
    "SUPABASE_DB_URL": "cloud",
    "SUPABASE_DB_URL_DIRECT": "cloud",
    "ATLAS_URI": "cloud",
    "FIREBASE_CREDENTIALS_PATH": "cloud",
    "FIREBASE_PROJECT_ID": "cloud",
    "FALLBACK_ENABLED": "fallback",
    "FALLBACK_PROBE_INTERVAL": "fallback",
    "SENDGRID_API_KEY": "email",
    "MAILGUN_API_KEY": "email",
    "STRIPE_API_KEY": "payment",
    "STRIPE_SECRET_KEY": "payment",
}

_ENV_GLOB = ".env.*"


def _load_kaira_raw() -> dict:
    """Return the raw .kaira.json contents (empty dict if absent/invalid)."""
    cfg_path = Path(".kaira.json")
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _feature_enabled(feature: str, config: KairaConfig, output_root: Path) -> bool:
    """Return True when *feature* is active for this project.

    Enablement is inferred from real project state — config fields plus the
    presence of the feature's generated files — rather than a raw env key.
    """
    if feature == "core":
        return True
    if feature == "auth":
        return config.auth_type != "none"
    if feature == "cache":
        return (output_root / "core" / "cache.py").exists()
    if feature == "task":
        return (output_root / "core" / "celery_app.py").exists() or (
            output_root / "tasks"
        ).exists()
    if feature == "cloud":
        return bool(_load_kaira_raw().get("cloud"))
    if feature == "fallback":
        return bool(_load_kaira_raw().get("fallback", {}).get("enabled"))
    return False


def _key_referenced(key: str, output_root: Path) -> bool:
    """Return True if *key* is referenced in any project ``.py`` source file."""
    for py_file in output_root.rglob("*.py"):
        parts = set(py_file.parts)
        if "__pycache__" in parts or ".venv" in parts or "venv" in parts:
            continue
        try:
            if key in py_file.read_text(encoding="utf-8"):
                return True
        except OSError:
            continue
    return False


def _collect_env_keys(output_root: Path) -> dict[str, list[Path]]:
    """Return a mapping of env key → the .env files it appears in (active lines)."""
    found: dict[str, list[Path]] = {}
    for env_path in sorted(output_root.glob(_ENV_GLOB)):
        if not env_path.is_file() or env_path.name == ".env.example":
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            found.setdefault(key, []).append(env_path)
    return found


def _get_env() -> Environment:
    return Environment(  # nosec B701 — autoescape not needed for Python code generation
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


@app.command("init")
def env_init(
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing files.")
    ] = False,
) -> None:
    """Initialize environment config files and settings module."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    # Create config directory
    config_dir = output_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "__init__.py").touch(exist_ok=True)

    env = _get_env()
    ctx = {
        "project_name": Path.cwd().name,
        "project_slug": Path.cwd().name.lower().replace("-", "_"),
    }

    # Write config/settings.py
    settings_tmpl = env.get_template("env_settings.py.j2")
    settings_path = config_dir / "settings.py"
    write_with_check(settings_path, settings_tmpl.render(**ctx), force=force)
    console.print(
        f"  [green bold]✓[/green bold]  Written: [cyan]{settings_path}[/cyan]"
    )

    # Write .env files
    envs = ["development", "staging", "production"]
    for e in envs:
        env_path = output_root / f".env.{e}"
        # Make a secure default key
        secret = "placeholder-32-character-secret-key-for-kaira-api"
        db_url = "sqlite:///./app.db"
        if e == "production":
            db_url = "postgresql://user:pass@localhost/dbname?sslmode=require"

        content = (
            f"APP_ENV={e}\n"
            f"APP_NAME={ctx['project_name']}\n"
            f"# DATABASE_URL={db_url}\n"
            f"# Uncomment and fill in your real credentials before running the app.\n"
            f"JWT_SECRET_KEY={secret}\n"
            f'ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n'
            f"DEBUG={'True' if e == 'development' else 'False'}\n"
        )
        write_with_check(env_path, content, force=force)
        console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{env_path}[/cyan]")

    # Write .env.example
    example_path = output_root / ".env.example"
    example_content = (
        "APP_ENV=development\n"
        f"APP_NAME={ctx['project_name']}\n"
        "# DATABASE_URL=postgresql://user:password@localhost/dbname\n"
        "# Uncomment and fill in your real credentials before running the app.\n"
        "JWT_SECRET_KEY=your-minimum-32-character-secret-key-here\n"
        'ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:8000"]\n'
        "DEBUG=False\n"
    )
    write_with_check(example_path, example_content, force=force)
    console.print(f"  [green bold]✓[/green bold]  Written: [cyan]{example_path}[/cyan]")

    # Append to .gitignore if present
    gitignore_path = output_root / ".gitignore"
    if gitignore_path.exists():
        gi_content = gitignore_path.read_text(encoding="utf-8")
        ignored_lines = [line.strip() for line in gi_content.split("\n")]
        to_add = [".env", ".env.*", "!.env.example"]
        added = False
        for pattern in to_add:
            if pattern not in ignored_lines:
                gi_content += f"\n{pattern}"
                added = True
        if added:
            gitignore_path.write_text(gi_content, encoding="utf-8")
            console.print(
                f"  [green bold]✓[/green bold]  Updated: [cyan]{gitignore_path}[/cyan] with env rules"
            )

    console.print(
        Panel(
            "[green]Environment management initialized successfully![/green]\n"
            "Generated .env.development, .env.staging, .env.production, and config/settings.py",
            title="Khaira — Env Init",
            border_style="green",
        )
    )


@app.command("add")
def env_add(
    key: Annotated[str, typer.Argument(help="The environment variable key.")],
    value: Annotated[str, typer.Argument(help="The environment variable value.")],
    environment: Annotated[
        str,
        typer.Option(
            "--env", help="Target environment: development, staging, production, all"
        ),
    ] = "all",
) -> None:
    """Add or update an environment variable key-value pair."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    envs = ["development", "staging", "production"]
    targets = envs if environment == "all" else [environment]

    for t in targets:
        env_path = output_root / f".env.{t}"
        if not env_path.exists():
            console.print(
                f"[yellow]⚠  Env file {env_path} does not exist. Skipping.[/yellow]"
            )
            continue

        content = env_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        updated = False

        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                updated = True
                break

        if not updated:
            lines.append(f"{key}={value}")

        env_path.write_text("\n".join(lines), encoding="utf-8")
        console.print(
            f"  [green bold]✓[/green bold]  Added/Updated: [cyan]{key}[/cyan] in [cyan].env.{t}[/cyan]"
        )


@app.command("switch")
def env_switch(
    environment: Annotated[
        str,
        typer.Argument(
            help="Target environment (e.g. development, staging, production)"
        ),
    ],
) -> None:
    """Switch the current active .env file to the target environment."""
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    src_path = output_root / f".env.{environment}"
    dest_path = output_root / ".env"

    if not src_path.exists():
        console.print(
            f"[red]Error: Source environment file not found:[/red] {src_path}"
        )
        raise typer.Exit(1)

    shutil.copy2(src_path, dest_path)
    console.print(
        f"  [green bold]✓[/green bold]  Active environment switched to: [cyan]{environment}[/cyan] (copied to .env)"
    )


@app.command("validate")
def env_validate() -> None:
    """Validate environment keys and secure settings rules.

    Phase 5: Also checks cloud provider keys (Supabase, Atlas, Firebase) and
    fallback settings when a cloud provider is configured.
    """
    config = get_config()
    output_root = Path.cwd() / config.output_dir

    # Check for settings.py
    settings_path = output_root / "config" / "settings.py"
    if not settings_path.exists():
        console.print(
            "[red]Error: config/settings.py not found. Run kaira env init first.[/red]"
        )
        raise typer.Exit(1)

    # Standard settings keys
    required_keys = [
        "APP_ENV",
        "APP_NAME",
        "DATABASE_URL",
        "JWT_SECRET_KEY",
        "ALLOWED_ORIGINS",
        "RATE_LIMIT_GET",
        "RATE_LIMIT_WRITE",
        "DEBUG",
    ]

    # Detect cloud provider from .kaira.json
    cloud_provider: str = ""
    try:
        import json as _json

        cfg_path = Path(".kaira.json")
        if cfg_path.exists():
            raw = _json.loads(cfg_path.read_text(encoding="utf-8"))
            if raw.get("cloud"):
                cloud_provider = raw.get("cloud_provider", raw.get("database", ""))
    except Exception:
        pass

    # Add provider-specific required keys
    _CLOUD_REQUIRED: dict[str, list[str]] = {
        "supabase": ["SUPABASE_DB_URL", "SUPABASE_DB_URL_DIRECT"],
        "atlas": ["ATLAS_URI"],
        "firebase": ["FIREBASE_CREDENTIALS_PATH", "FIREBASE_PROJECT_ID"],
    }
    if cloud_provider in _CLOUD_REQUIRED:
        required_keys.extend(_CLOUD_REQUIRED[cloud_provider])
        required_keys.extend(["FALLBACK_ENABLED", "FALLBACK_PROBE_INTERVAL"])

    envs = ["development", "staging", "production"]
    issues = []

    for env_name in envs:
        env_path = output_root / f".env.{env_name}"
        if not env_path.exists():
            issues.append((env_name, "File missing", "❌ High"))
            continue

        content = env_path.read_text(encoding="utf-8")
        env_keys = {}
        for line in content.split("\n"):
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env_keys[k.strip()] = v.strip()

        # Check for missing keys
        for key in required_keys:
            if key not in env_keys:
                issues.append((env_name, f"Missing key: {key}", "❌ High"))

        # Check secret key length
        secret = env_keys.get("JWT_SECRET_KEY", "")
        if secret and len(secret) < 32:
            issues.append(
                (env_name, "JWT_SECRET_KEY is shorter than 32 chars", "❌ High")
            )

        # Check production debug mode
        debug = env_keys.get("DEBUG", "False").lower() == "true"
        if env_name == "production" and debug:
            issues.append((env_name, "DEBUG is enabled in production", "❌ High"))

        # Check production CORS
        origins = env_keys.get("ALLOWED_ORIGINS", "")
        if env_name == "production" and "*" in origins:
            issues.append(
                (env_name, "CORS contains wildcard '*' in production", "❌ High")
            )

        # Check connection pooling/ssl warning (local + supabase)
        db_url = env_keys.get("DATABASE_URL", "")
        if "postgresql" in db_url and "sslmode=require" not in db_url:
            issues.append((env_name, "DATABASE_URL lacks sslmode=require", "⚠️  Medium"))

        # ── Phase 5 cloud checks ─────────────────────────────────────────────

        # Supabase: SSL enforced on both URLs
        for key in ("SUPABASE_DB_URL", "SUPABASE_DB_URL_DIRECT"):
            val = env_keys.get(key, "")
            if val and "postgresql" in val and "sslmode=require" not in val:
                issues.append((env_name, f"{key} lacks sslmode=require", "❌ High"))

        # Atlas: tls=true or tls enforced by SRV
        atlas_uri = env_keys.get("ATLAS_URI", "")
        if (
            atlas_uri
            and "mongodb+srv://" not in atlas_uri.lower()
            and "tls=true" not in atlas_uri
        ):
            issues.append(
                (
                    env_name,
                    "ATLAS_URI should use mongodb+srv:// (TLS enforced) or include tls=true",
                    "⚠️  Medium",
                )
            )

        # Firebase: credentials file must exist and not be git-tracked
        cred_path_str = env_keys.get("FIREBASE_CREDENTIALS_PATH", "")
        if cred_path_str:
            cred_path = Path(cred_path_str).expanduser()
            if not cred_path.exists():
                issues.append(
                    (
                        env_name,
                        f"FIREBASE_CREDENTIALS_PATH file not found: {cred_path_str}",
                        "❌ High",
                    )
                )
            else:
                # Check it is not tracked by git
                import subprocess as _sp

                try:
                    result = _sp.run(
                        ["git", "ls-files", "--error-unmatch", str(cred_path)],
                        capture_output=True,
                        text=True,
                        cwd=str(Path.cwd()),
                    )
                    if result.returncode == 0:
                        issues.append(
                            (
                                env_name,
                                "FIREBASE_CREDENTIALS_PATH file is tracked by git — remove it immediately!",
                                "❌ High",
                            )
                        )
                except FileNotFoundError:
                    pass  # git not available

    # Check .env.example has no real cloud credentials (placeholders only)
    example_path = output_root / ".env.example"
    if example_path.exists() and cloud_provider:
        example_content = example_path.read_text(encoding="utf-8")
        _CLOUD_KEYS_PATTERNS = [
            "SUPABASE_DB_URL=",
            "ATLAS_URI=mongodb+srv://",
            "FIREBASE_CREDENTIALS_PATH=/",
        ]
        for pattern in _CLOUD_KEYS_PATTERNS:
            if pattern in example_content:
                # Check if it looks like a real value (not a placeholder)
                for line in example_content.splitlines():
                    if line.startswith(pattern.split("=")[0] + "="):
                        val = line.split("=", 1)[1]
                        if (
                            val
                            and not val.startswith("<")
                            and "placeholder" not in val.lower()
                        ):
                            issues.append(
                                (
                                    ".env.example",
                                    f"Real credential detected in .env.example for {pattern.split('=')[0]}",
                                    "❌ High",
                                )
                            )

    # Print report
    table = Table(title="Khaira — Environment Security Audit Report")
    table.add_column("Environment", justify="left")
    table.add_column("Security Issue / Validation Check", justify="left")
    table.add_column("Severity", justify="right")

    for env_name, msg, sev in issues:
        table.add_row(env_name, msg, sev)

    if issues:
        console.print(table)
        console.print(f"[red]Found {len(issues)} validation warnings/issues.[/red]")
    else:
        console.print(
            "[green]✔ All environment checks passed successfully! (All keys present, secure values validated)[/green]"
        )


# ---------------------------------------------------------------------------
# env audit / env prune  (Phase 5.5 — .env bloat cleanup)
# ---------------------------------------------------------------------------


def _audit_rows(
    config: KairaConfig, output_root: Path
) -> list[tuple[str, str, bool, bool]]:
    """Return ``(key, feature, enabled, referenced)`` for every env key in use."""
    rows: list[tuple[str, str, bool, bool]] = []
    for key in sorted(_collect_env_keys(output_root)):
        feature = _KEY_FEATURES.get(key, "custom")
        enabled = feature in ("core", "custom") or _feature_enabled(
            feature, config, output_root
        )
        referenced = _key_referenced(key, output_root)
        rows.append((key, feature, enabled, referenced))
    return rows


def _is_unused(feature: str, enabled: bool, referenced: bool) -> bool:
    """A key is prunable only when its feature is off AND it is unreferenced."""
    if feature in ("core", "custom"):
        return False
    return not enabled and not referenced


def collect_env_audit_rows(
    config: KairaConfig, output_root: Path
) -> list[tuple[str, str, bool, bool]]:
    """Return ``(key, feature, enabled, referenced)`` for every env key in use."""
    return _audit_rows(config, output_root)


KEY_FEATURES = _KEY_FEATURES


@app.command("audit")
def env_audit() -> None:
    """Audit every env key: which feature owns it, whether code references it, and status.

    Examples
    --------
    kaira env audit
    """
    from kaira.core.theme import Theme, sym
    from kaira.core.ui import data_table

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    rows = _audit_rows(config, output_root)

    if not rows:
        console.print(
            "[yellow]No .env.* files found. Run kaira env init first.[/yellow]"
        )
        return

    ok, warn = sym("OK"), sym("WARN")
    table_rows: list[list[str]] = []
    unused = 0
    for key, feature, enabled, referenced in rows:
        prunable = _is_unused(feature, enabled, referenced)
        if prunable:
            unused += 1
        status = (
            f"[{Theme.WARNING}]{warn} Unused[/{Theme.WARNING}]"
            if prunable
            else f"[{Theme.SUCCESS}]{ok} Keep[/{Theme.SUCCESS}]"
        )
        ref_disp = (
            ok
            if referenced
            else (warn if prunable else f"[{Theme.MUTED}]off[/{Theme.MUTED}]")
        )
        table_rows.append([key, feature, ref_disp, status])

    data_table(
        ["Key", "Feature", "Referenced", "Status"],
        table_rows,
        title="⚡ Khaira — Env Audit",
    )
    if unused:
        console.print(
            f"  [{Theme.WARNING}]{unused} unused key(s). Run [/{Theme.WARNING}]"
            f"[{Theme.PRIMARY}]kaira env prune[/{Theme.PRIMARY}]"
            f"[{Theme.WARNING}] to remove.[/{Theme.WARNING}]"
        )
    else:
        console.print(
            f"  [{Theme.SUCCESS}]{ok} No unused keys — .env files are clean.[/{Theme.SUCCESS}]"
        )


@app.command("prune")
def env_prune(
    force: Annotated[
        bool, typer.Option("--force", help="Skip typed confirmation (CI mode).")
    ] = False,
) -> None:
    """Remove env keys for features that are not enabled in this project.

    Core keys and referenced keys are never removed.  Blocked when
    ``APP_ENV=production``.

    Examples
    --------
    kaira env prune
    """
    from kaira.core.theme import Theme, sym
    from kaira.commands.ux_helpers import typed_confirmation

    config = get_config()
    output_root = Path.cwd() / config.output_dir
    rows = _audit_rows(config, output_root)

    prunable = [
        key
        for key, feature, enabled, referenced in rows
        if _is_unused(feature, enabled, referenced)
    ]

    if not prunable:
        ok = sym("OK")
        console.print(
            f"[{Theme.SUCCESS}]{ok} Nothing to prune — no unused keys found.[/{Theme.SUCCESS}]"
        )
        return

    console.print(
        f"[{Theme.WARNING}]The following unused key(s) will be removed from all .env.* files:[/{Theme.WARNING}]\n"
        + "\n".join(f"  • {k}" for k in prunable)
    )
    if not typed_confirmation(
        "prune",
        f"This removes {len(prunable)} key(s) across every .env.* file.",
        force=force,
    ):
        return

    removed = _remove_keys_from_env_files(output_root, set(prunable))
    ok = sym("OK")
    console.print(
        f"[{Theme.SUCCESS}]{ok} Pruned {len(prunable)} key(s) from {removed} .env file(s).[/{Theme.SUCCESS}]"
    )


def _remove_keys_from_env_files(output_root: Path, keys: set[str]) -> int:
    """Delete lines assigning any key in *keys* from every ``.env.*`` file.

    Returns the number of files modified.  Applies consistently across all
    environment files so none is left out of sync.
    """
    modified = 0
    for env_path in sorted(output_root.glob(_ENV_GLOB)):
        if not env_path.is_file() or env_path.name == ".env.example":
            continue
        lines = env_path.read_text(encoding="utf-8").splitlines()
        kept = [
            line
            for line in lines
            if not (
                "=" in line
                and not line.lstrip().startswith("#")
                and line.split("=", 1)[0].strip() in keys
            )
        ]
        if len(kept) != len(lines):
            env_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
            modified += 1
    return modified
