"""Auto database provisioning for Kaira (Phase 6, Feature 1).

Detects a local database *server* (never a GUI client), sanitizes the project
name into a valid database identifier, resolves credentials passwordless-first,
and creates the database idempotently. When no server is reachable — or the
user declines to authenticate — it degrades to an offline SQLite fallback so
``kaira init`` always completes.

The pure helpers (:func:`sanitize_db_name`, :func:`is_valid_identifier`,
:func:`offline_sqlite_url`, :func:`pick_signal`) are separated from all I/O so
they can be unit-tested without a live database.

Security invariants (see Phase 6 §5):
- Never guess or write a fake password. Passwordless-first; prompt via
  :func:`kaira.core.prompts.secret` only when the server rejects auth.
- Every printed DSN and every driver error is masked via
  :func:`kaira.commands.ux_helpers.mask_credentials`.
- The database identifier is validated against ``^[a-z_][a-z0-9_]*$`` before it
  is ever used in DDL — no raw f-string SQL with an interpolated name.
"""

from __future__ import annotations

import re
import shutil
import socket
from dataclasses import dataclass
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Engine metadata
# ---------------------------------------------------------------------------

#: The database *server* CLI to look for on ``PATH`` per engine. These are the
#: servers' shells — never GUI clients like pgAdmin/Compass/Workbench.
SERVER_CLIENTS: dict[str, str] = {
    "postgresql": "psql",
    "mysql": "mysql",
    "mongodb": "mongosh",
}

#: Default listening port per engine, used for the TCP probe.
DEFAULT_PORTS: dict[str, int] = {
    "postgresql": 5432,
    "mysql": 3306,
    "mongodb": 27017,
}

#: Default localhost superuser/admin per engine when none is supplied.
DEFAULT_USERS: dict[str, str] = {
    "postgresql": "postgres",
    "mysql": "root",
    "mongodb": "",  # local Mongo is typically no-auth
}

#: Maximum identifier length accepted by each engine.
MAX_NAME_LEN: dict[str, int] = {
    "postgresql": 63,
    "mysql": 64,
    "mongodb": 64,
}

RELATIONAL = {"postgresql", "mysql", "sqlite"}

#: Strict allowlist every database identifier must satisfy before use in DDL.
_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Where the offline SQLite database lives, relative to the project root.
OFFLINE_DB_PATH = "./.kaira/offline.db"
OFFLINE_SQLITE_URL = f"sqlite+aiosqlite:///{OFFLINE_DB_PATH}"


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — unit-testable)
# ---------------------------------------------------------------------------


def is_valid_identifier(name: str) -> bool:
    """Return True if *name* is a safe database identifier.

    Enforces ``^[a-z_][a-z0-9_]*$``. This is the injection guard applied before
    any name is interpolated into ``CREATE DATABASE`` DDL.

    Args:
        name: Candidate identifier.

    Returns:
        True when the name matches the strict allowlist.
    """
    return bool(_IDENTIFIER_RE.fullmatch(name))


def sanitize_db_name(project_name: str, engine: str) -> str:
    """Convert a project name into a valid database identifier for *engine*.

    Rules (Phase 6 §1.2):
    - lowercase; ``-``, space, and ``.`` become ``_``;
    - any other character not in ``[a-z0-9_]`` is dropped (covers Mongo's
      forbidden ``/\\."$*<>:|?`` set as well);
    - collapse repeated underscores; strip leading digits/underscores so the
      result starts with ``[a-z_]``; truncate to the engine's max length.

    ``philceb-api`` becomes ``philceb_api``.

    Args:
        project_name: The raw project name.
        engine: One of ``postgresql``/``mysql``/``mongodb``/``sqlite``.

    Returns:
        A sanitized identifier guaranteed to satisfy :func:`is_valid_identifier`.
    """
    lowered = project_name.strip().lower()
    # Map separators to underscore, drop everything else outside the allowlist.
    mapped = re.sub(r"[-.\s]", "_", lowered)
    cleaned = re.sub(r"[^a-z0-9_]", "", mapped)
    # Collapse repeated underscores for readability.
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    # Identifiers must start with a letter or underscore — strip leading digits.
    cleaned = cleaned.lstrip("0123456789")
    cleaned = cleaned.strip("_") or "db"
    if not cleaned[0].isalpha() and cleaned[0] != "_":
        cleaned = f"db_{cleaned}"
    max_len = MAX_NAME_LEN.get(engine, 63)
    cleaned = cleaned[:max_len].rstrip("_") or "db"
    return cleaned


def offline_sqlite_url() -> str:
    """Return the offline SQLite DSN used as the fallback store."""
    return OFFLINE_SQLITE_URL


def offline_store_url(engine: str, db_name: str) -> str:
    """Return the offline store DSN that matches *engine*'s data-model family.

    Relational engines (Postgres/MySQL/SQLite) mirror to SQLite — models are
    portable. MongoDB is a document store, so it never mirrors to SQLite
    (Phase 6 §3.3); its offline store is a local MongoDB namespace.

    Args:
        engine: The project's primary engine.
        db_name: Sanitized database name (used for the Mongo offline namespace).

    Returns:
        A DSN for the offline store appropriate to the engine family.
    """
    if engine == "mongodb":
        return f"mongodb://localhost:27017/{db_name}_offline"
    return OFFLINE_SQLITE_URL


def offline_engine_name(engine: str) -> str:
    """Return the engine name the offline store presents as."""
    return "mongodb" if engine == "mongodb" else "sqlite"


#: Postgres-native column types SQLite cannot faithfully represent (§3.4).
POSTGRES_NATIVE_TYPES = (
    "jsonb",
    "array",
    "uuid",
    "enum",
    "inet",
    "cidr",
    "tsvector",
    "gen_random_uuid",
)


def models_with_native_types(models: list[dict]) -> list[str]:
    """Return names of models whose fields use a Postgres-native column type.

    Kaira's default templates are portable (String/Int/DateTime/UUID-as-string),
    so this normally returns ``[]``. It exists as a flag-only safety net for
    hand-edited models before an offline-SQLite run (§3.4).

    Args:
        models: The ``generated_models`` list from ``.kaira.json``.

    Returns:
        Model names that reference a native type; empty when all are portable.
    """
    flagged: list[str] = []
    for model in models:
        name = model.get("name", "?")
        for fld in model.get("fields", []):
            type_str = str(fld.get("type", "")).lower()
            if any(nt in type_str for nt in POSTGRES_NATIVE_TYPES):
                flagged.append(name)
                break
    return flagged


def pick_signal(has_client: bool, port_open: bool, driver_ok: bool) -> str:
    """Return the winning detection signal, first hit wins.

    Order per Phase 6 §1.1: ``client`` (server shell on PATH) → ``port`` (TCP
    probe) → ``driver`` (a real connect). ``none`` when nothing succeeded.

    Args:
        has_client: ``shutil.which`` found the server shell.
        port_open: The default TCP port accepted a connection.
        driver_ok: A driver connect succeeded.

    Returns:
        ``"client"`` | ``"port"`` | ``"driver"`` | ``"none"``.
    """
    if has_client:
        return "client"
    if port_open:
        return "port"
    if driver_ok:
        return "driver"
    return "none"


def default_dsn(
    engine: str,
    db_name: str,
    *,
    password: str = "",
    user: str = "",
    host: str = "localhost",
    port: Optional[int] = None,
) -> str:
    """Build a DSN for *engine* pointing at *db_name*.

    Credentials are embedded only when supplied; passwordless connections omit
    them entirely so we never write a fake ``postgres:postgres`` pair.

    Args:
        engine: Target engine.
        db_name: The (already sanitized) database name.
        password: Optional password; omitted from the DSN when blank.
        user: Optional user; defaults to the engine's localhost default.
        host: Database host (default: localhost).
        port: Database port.

    Returns:
        A DSN string. Never contains ``:@`` when the password is blank.
    """
    user = user or DEFAULT_USERS.get(engine, "")
    eff_port = port if port is not None else DEFAULT_PORTS.get(engine, 0)
    if engine == "postgresql":
        auth = f"{user}:{password}@" if password else (f"{user}@" if user else "")
        return f"postgresql+asyncpg://{auth}{host}:{eff_port}/{db_name}"
    if engine == "mysql":
        auth = f"{user}:{password}@" if password else (f"{user}@" if user else "")
        return f"mysql+aiomysql://{auth}{host}:{eff_port}/{db_name}"
    if engine == "mongodb":
        auth = f"{user}:{password}@" if (user and password) else ""
        return f"mongodb://{auth}{host}:{eff_port}/{db_name}"
    return OFFLINE_SQLITE_URL


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    """Outcome of server detection for a single engine."""

    engine: str
    reachable: bool
    signal: str  # "client" | "port" | "driver" | "none"
    detail: str  # human-readable, e.g. "psql · port 5432"
    host: str = "localhost"
    port: int = 0


@dataclass
class ProvisionResult:
    """Outcome of a provisioning attempt."""

    ok: bool
    mode: str  # "online" | "offline"
    engine: str  # effective engine (sqlite when offline fallback taken)
    db_name: str
    dsn: str
    offline: bool
    message: str
    created: bool = False
    password_entered: bool = False
    manual_sql: Optional[str] = None


# ---------------------------------------------------------------------------
# Detection (I/O, but dependency-injected for tests)
# ---------------------------------------------------------------------------


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to ``host:port`` succeeds within *timeout*."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_server(
    engine: str,
    *,
    host: str = "localhost",
    which: Callable[[str], Optional[str]] = shutil.which,
    port_probe: Callable[[str, int, float], bool] = _port_open,
) -> Detection:
    """Detect a local *server* for *engine*, reporting the winning signal.

    Detection never keys off GUI clients (pgAdmin/Compass/Workbench). The
    dependencies (``which``/``port_probe``) are injectable so tests can drive
    every branch without a real server.

    Args:
        engine: ``postgresql`` | ``mysql`` | ``mongodb``.
        host: Host to probe (default ``localhost``).
        which: Callable resolving a binary on ``PATH`` (default ``shutil.which``).
        port_probe: Callable ``(host, port, timeout) -> bool``.

    Returns:
        A :class:`Detection` describing reachability and the winning signal.
    """
    if engine == "sqlite":
        return Detection(engine, True, "client", "sqlite (file-based)", host, 0)

    client = SERVER_CLIENTS.get(engine)
    port = DEFAULT_PORTS.get(engine, 0)
    has_client = bool(client and which(client))
    port_open = port_probe(host, port, 2.0) if port else False
    signal = pick_signal(has_client, port_open, False)

    if signal == "none":
        return Detection(
            engine, False, "none", f"no {engine} server on {host}", host, port
        )

    detail_parts = []
    if has_client:
        detail_parts.append(str(client))
    if port_open:
        detail_parts.append(f"port {port}")
    detail = "  ·  ".join(detail_parts) or engine
    return Detection(engine, True, signal, detail, host, port)


# ---------------------------------------------------------------------------
# Idempotent creation (I/O)
# ---------------------------------------------------------------------------


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run *coro* on a private event loop and return its result."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class AuthError(Exception):
    """Raised when the server rejects the supplied credentials."""


class PrivilegeError(Exception):
    """Raised when the connected user lacks CREATE DATABASE privileges."""


async def _pg_create(dsn_admin: str, db_name: str) -> bool:
    """Create a Postgres database idempotently. Returns True if newly created."""
    import asyncpg  # type: ignore[import]

    # Connect to the maintenance DB, not the target (which may not exist yet).
    try:
        conn = await asyncpg.connect(dsn_admin, timeout=5)
    except asyncpg.InvalidPasswordError as exc:  # pragma: no cover - env-specific
        raise AuthError(str(exc)) from exc
    except asyncpg.InvalidAuthorizationSpecificationError as exc:  # pragma: no cover
        raise AuthError(str(exc)) from exc
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if exists:
            return False
        if not is_valid_identifier(db_name):
            raise ValueError(f"unsafe identifier: {db_name!r}")
        # Name already validated against the allowlist; asyncpg has no bind for
        # DDL identifiers, so the vetted literal is safe to inline.
        await conn.execute(f'CREATE DATABASE "{db_name}"')
        return True
    except Exception as exc:  # noqa: BLE001 — mapped to a typed error below
        msg = str(exc).lower()
        if "permission denied" in msg or "must be" in msg:
            raise PrivilegeError(str(exc)) from exc
        raise
    finally:
        await conn.close()


async def _mysql_create(
    host: str, port: int, user: str, password: str, db_name: str
) -> bool:
    """Create a MySQL database idempotently. Returns True if newly created."""
    import aiomysql  # type: ignore[import]

    try:
        conn = await aiomysql.connect(
            host=host, port=port, user=user, password=password, connect_timeout=5
        )
    except Exception as exc:  # noqa: BLE001
        if "access denied" in str(exc).lower():
            raise AuthError(str(exc)) from exc
        raise
    try:
        async with conn.cursor() as cur:
            await cur.execute("SHOW DATABASES LIKE %s", (db_name,))
            if await cur.fetchone():
                return False
            if not is_valid_identifier(db_name):
                raise ValueError(f"unsafe identifier: {db_name!r}")
            try:
                await cur.execute(f"CREATE DATABASE `{db_name}`")
            except Exception as exc:  # noqa: BLE001
                if "denied" in str(exc).lower():
                    raise PrivilegeError(str(exc)) from exc
                raise
        return True
    finally:
        conn.close()


async def _mongo_ping(host: str, port: int) -> bool:
    """Confirm a Mongo server is reachable. Mongo creates DBs lazily on write."""
    from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore[import]

    client = AsyncIOMotorClient(host=host, port=port, serverSelectionTimeoutMS=2000)
    try:
        await client.admin.command("ping")
        return True
    finally:
        client.close()


def manual_create_sql(engine: str, db_name: str) -> str:
    """Return the exact SQL to create *db_name* by hand after a privilege failure."""
    if engine == "mysql":
        return f"CREATE DATABASE `{db_name}`;"
    return f"CREATE DATABASE {db_name};"


def _create_dispatch(
    engine: str, host: str, port: int, user: str, password: str, db_name: str
) -> bool:
    """Attempt to create *db_name* on the running server. Returns True if created.

    Raises:
        AuthError: The server rejected the credentials.
        PrivilegeError: The user cannot create databases.
        ImportError: The async driver is not installed in this environment.
    """
    if engine == "postgresql":
        # asyncpg wants a plain libpq DSN — never the SQLAlchemy "+asyncpg" form.
        # Connect to the maintenance DB "postgres"; the target may not exist yet.
        auth = f"{user}:{password}@" if password else (f"{user}@" if user else "")
        dsn_admin = f"postgresql://{auth}{host}:{port}/postgres"
        return _run_async(_pg_create(dsn_admin, db_name))
    if engine == "mysql":
        return _run_async(_mysql_create(host, port, user, password, db_name))
    if engine == "mongodb":
        # Mongo has no create step — provisioning is a reachability confirmation.
        return _run_async(_mongo_ping(host, port))
    raise ValueError(f"unsupported engine: {engine}")


@dataclass
class PasswordPromptContext:
    """Everything the password prompt must show the user before asking."""

    engine: str
    host: str
    port: int
    user: str
    db_name: str
    attempt: int  # 1-based
    max_attempts: int
    last_error: bool  # True when re-prompting after a failed attempt


def provision_database(
    engine: str,
    project_name: str,
    *,
    db_name: Optional[str] = None,
    host: str = "localhost",
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    skip: bool = False,
    env_password: Optional[str] = None,
    prompt_password: Optional[Callable[[PasswordPromptContext], Optional[str]]] = None,
    confirm_create: Optional[Callable[[str], bool]] = None,
    announce: Callable[[str], None] = lambda _m: None,
    detector: Callable[..., Detection] = detect_server,
    creator: Optional[Callable[..., bool]] = None,
    max_attempts: int = 3,
) -> ProvisionResult:
    """Provision a database for *project_name*, falling back to offline SQLite.

    This is the orchestration heart of Feature 1. Every side-effecting
    dependency is injectable so the full decision tree (detect → passwordless →
    prompt → retry → create → privilege failure → offline fallback) is testable
    without a real server or a TTY.

    Args:
        engine: Target engine (``postgresql``/``mysql``/``mongodb``/``sqlite``).
        project_name: Raw project name; sanitized into the DB name.
        db_name: Explicit name override (already-sanitized names are re-validated).
        host: Host to detect/connect (default ``localhost``).
        skip: Scaffold the DSN only; never touch the server (``db create --skip``
            and the ``scale`` profile).
        env_password: Password already available from the environment
            (``PGPASSWORD``/``MYSQL_PWD`` or embedded in ``DATABASE_URL``).
        prompt_password: Callback returning a password, or ``None`` to skip
            (blank submission → offline fallback). ``None`` here means
            non-interactive: never prompt.
        confirm_create: Callback asking whether to create the database; ``None``
            means "assume yes" (``--yes``/``solo`` path).
        announce: Callback for user-facing status lines.
        detector: Server-detection function (injected in tests).
        creator: Create function ``(engine, host, port, user, password, name)``
            returning ``bool`` (injected in tests); defaults to the real driver.

    Returns:
        A :class:`ProvisionResult`. ``ok`` is True whenever ``init`` can proceed
        (either the DB is provisioned online or the offline fallback was taken).
    """
    name = db_name or sanitize_db_name(project_name, engine)
    if not is_valid_identifier(name):
        # Should be impossible via sanitize_db_name; guards an explicit --name.
        return ProvisionResult(
            ok=False,
            mode="offline",
            engine=engine,
            db_name=name,
            dsn=OFFLINE_SQLITE_URL,
            offline=True,
            message=f"invalid database name {name!r} — must match ^[a-z_][a-z0-9_]*$",
        )

    if db_name is None and name != _plain_slug(project_name):
        announce(f'sanitized · project name → database "{name}"')

    # SQLite is file-based: nothing to provision on a server.
    if engine == "sqlite":
        dsn = f"sqlite+aiosqlite:///./{name}.db"
        return ProvisionResult(
            ok=True,
            mode="online",
            engine="sqlite",
            db_name=name,
            dsn=dsn,
            offline=False,
            message="sqlite · file-based, no server provisioning needed",
        )

    if skip:
        return ProvisionResult(
            ok=True,
            mode="online",
            engine=engine,
            db_name=name,
            dsn=default_dsn(engine, name),
            offline=False,
            message="scaffolded · DSN only (--skip / scale profile), server not touched",
        )

    # ── 1. Detect the server ─────────────────────────────────────────────────
    detection = detector(engine, host=host)
    if not detection.reachable:
        announce(f"unreachable · no {engine} server on {host}")
        return _offline_result(engine, name, reason=f"no {engine} server reachable")
    announce(f"detected · {engine} {detection.detail}")

    port = port or detection.port or DEFAULT_PORTS.get(engine, 0)
    user = user or DEFAULT_USERS.get(engine, "")
    do_create = creator or _create_dispatch

    # ── 2. Passwordless-first (or explicitly provided) ────────────────────────
    first_password = password or env_password or ""
    try:
        created = do_create(engine, host, port, user, first_password, name)
        return _created_result(
            engine,
            name,
            host,
            port,
            user,
            first_password,
            created,
            password_entered=bool(password),
        )
    except AuthError:
        pass  # fall through to the prompt
    except PrivilegeError as exc:
        return _privilege_result(engine, name, host, port, user, first_password, exc)
    except ImportError:
        announce(f"driver missing · {engine} · scaffolding DSN only")
        return ProvisionResult(
            ok=True,
            mode="online",
            engine=engine,
            db_name=name,
            dsn=default_dsn(engine, name, user=user),
            offline=False,
            message=f"driver missing · {engine} · DSN scaffolded, run `kaira db create` after installing",
        )

    # ── 3. Prompt for a password (interactive only), retry up to max_attempts ─
    if prompt_password is None:
        # Non-interactive / CI: never block on a prompt.
        env_var = "PGPASSWORD" if engine == "postgresql" else "MYSQL_PWD"
        announce(
            f"auth required · set {env_var} or put the password in "
            f"DATABASE_URL, then run `kaira db create`"
        )
        return _offline_result(engine, name, reason="auth required, non-interactive")

    for attempt in range(1, max_attempts + 1):
        ctx = PasswordPromptContext(
            engine=engine,
            host=host,
            port=port,
            user=user,
            db_name=name,
            attempt=attempt,
            max_attempts=max_attempts,
            last_error=attempt > 1,
        )
        password = prompt_password(ctx)
        if not password:
            # Blank = graceful skip → offline SQLite.
            announce("skipped · no password entered, using offline SQLite")
            return _offline_result(engine, name, reason="password skipped")
        try:
            created = do_create(engine, host, port, user, password, name)
            return _created_result(
                engine, name, host, port, user, password, created, password_entered=True
            )
        except AuthError:
            if attempt >= max_attempts:
                announce(f"auth failed · {max_attempts} attempts")
                return _offline_result(engine, name, reason="auth failed 3x")
            # loop re-prompts with an incremented attempt counter
        except PrivilegeError as exc:
            return _privilege_result(engine, name, host, port, user, password, exc)

    return _offline_result(engine, name, reason="auth exhausted")


def _plain_slug(project_name: str) -> str:
    """Lowercased project name for change-detection comparison in announcements."""
    return project_name.strip().lower()


def _offline_result(engine: str, name: str, *, reason: str) -> ProvisionResult:
    """Build the offline fallback result, matching the engine's data-model family."""
    store = offline_store_url(engine, name)
    eff_engine = offline_engine_name(engine)
    where = OFFLINE_DB_PATH if eff_engine == "sqlite" else "local mongodb"
    label = "offline SQLite" if eff_engine == "sqlite" else "offline local MongoDB"
    return ProvisionResult(
        ok=True,
        mode="offline",
        engine=eff_engine,
        db_name=name,
        dsn=store,
        offline=True,
        message=f"falling back to {label} at {where} ({reason})",
    )


def _created_result(
    engine: str,
    name: str,
    host: str,
    port: int,
    user: str,
    password: str,
    created: bool,
    *,
    password_entered: bool,
) -> ProvisionResult:
    """Build the success result for an online provision."""
    dsn = default_dsn(engine, name, password=password, user=user, host=host, port=port)
    if engine == "mongodb":
        msg = f'confirmed · mongodb server · "{name}" created lazily on first write'
    elif created:
        msg = f"created · {name} · user {user} · {host}:{port}"
    else:
        msg = f"exists · {name} · no changes"
    return ProvisionResult(
        ok=True,
        mode="online",
        engine=engine,
        db_name=name,
        dsn=dsn,
        offline=False,
        message=msg,
        created=created,
        password_entered=password_entered,
    )


def _privilege_result(
    engine: str,
    name: str,
    host: str,
    port: int,
    user: str,
    password: str,
    exc: Exception,
) -> ProvisionResult:
    """Build the privilege-failure result (scaffold continues, manual SQL shown)."""
    dsn = default_dsn(engine, name, password=password, user=user, host=host, port=port)
    return ProvisionResult(
        ok=True,
        mode="online",
        engine=engine,
        db_name=name,
        dsn=dsn,
        offline=False,
        created=False,
        message="cannot create database (insufficient privileges)",
        manual_sql=manual_create_sql(engine, name),
    )
