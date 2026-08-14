"""Docker project-state resolution and the compose services registry.

Docker configuration in Kaira is *reactive*: the generated Dockerfile and
compose files are a pure function of the project's state in ``.kaira.json``
plus what has actually been scaffolded on disk.  When the project gains Redis,
Celery, or a search provider, the compose files gain the matching services the
next time ``kaira docker sync`` runs.

Two structures carry the whole design:

``ProjectState``
    The normalised snapshot the templates render from.  Resolved from
    ``.kaira.json`` first, falling back to filesystem detection for features
    that predate the explicit flags.

``SERVICE_REGISTRY``
    An ordered list of :class:`ServiceDefinition` entries.  Each entry knows
    when it is enabled and how to build its compose service block(s).  The
    compose templates loop over the resulting list — they contain no per-feature
    ``if``/``elif`` chain — so a future feature plugs in by appending one
    registry entry rather than by rewriting a template.

This module is deliberately free of Rich, Typer, and Jinja imports: it is pure
state, so it can be imported from any command without circularity and unit
tested without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Base image pinning
# ---------------------------------------------------------------------------

SUPPORTED_PYTHON: list[str] = ["3.10", "3.11", "3.12", "3.13"]
"""Minor versions accepted by ``kaira docker init --python``."""

DEFAULT_PYTHON = "3.12"
"""Default Python minor version for generated Dockerfiles."""

PYTHON_PATCH: dict[str, str] = {
    "3.10": "3.10.16",
    "3.11": "3.11.11",
    "3.12": "3.12.8",
    "3.13": "3.13.1",
}
"""Minor version → pinned patch version.

Base images are pinned to a full patch version so a rebuild six months from now
produces the same image.  A minor-only tag such as ``python:3.12-slim`` silently
moves underneath the project, which is the same reproducibility hole as
``latest`` — just slower to notice.
"""


class InvalidPythonVersion(ValueError):
    """Raised when a requested Python version cannot be resolved to a tag."""


def resolve_python_version(value: Optional[str]) -> str:
    """Return a full ``X.Y.Z`` base-image version for *value*.

    Accepts a supported minor version (``"3.12"`` → the pinned patch) or an
    explicit full version (``"3.12.11"``), which is passed through untouched so
    a project can move ahead of Kaira's pin table without waiting for a release.

    Args:
        value: Minor or full version string; ``None``/empty selects the default.

    Returns:
        A full ``X.Y.Z`` version string.

    Raises:
        InvalidPythonVersion: If *value* is neither a supported minor version
            nor a well-formed full version.
    """
    if not value:
        value = DEFAULT_PYTHON
    value = value.strip().lstrip("v")

    parts = value.split(".")
    if len(parts) == 2:
        if value not in PYTHON_PATCH:
            raise InvalidPythonVersion(value)
        return PYTHON_PATCH[value]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        if f"{parts[0]}.{parts[1]}" not in PYTHON_PATCH:
            raise InvalidPythonVersion(value)
        return value
    raise InvalidPythonVersion(value)


# ---------------------------------------------------------------------------
# Database → system build dependencies
# ---------------------------------------------------------------------------

SYSTEM_BUILD_DEPS: dict[str, list[str]] = {
    "postgresql": ["gcc", "libpq-dev"],
    "postgres": ["gcc", "libpq-dev"],
    # Supabase is hosted PostgreSQL — same client library, same build deps.
    "supabase": ["gcc", "libpq-dev"],
    "mysql": ["gcc", "default-libmysqlclient-dev", "pkg-config"],
    "mariadb": ["gcc", "default-libmysqlclient-dev", "pkg-config"],
    # Pure-Python drivers — nothing to compile.
    "mongodb": [],
    "atlas": [],
    "sqlite": [],
    "firebase": [],
    "firestore": [],
}
"""``db_type`` → apt packages the builder stage needs.

A mapping rather than an if/else chain: a new database is one entry here, and
the Dockerfile template renders the ``apt-get`` block only when the list is
non-empty so an unnecessary layer is never created.
"""

DB_LABELS: dict[str, str] = {
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "supabase": "Supabase (hosted PostgreSQL)",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "mongodb": "MongoDB",
    "atlas": "MongoDB Atlas",
    "sqlite": "SQLite",
    "firebase": "Firebase (Firestore)",
    "firestore": "Firebase (Firestore)",
}

CLOUD_DATABASES = {"supabase", "atlas", "firebase", "firestore"}
"""Databases hosted outside the compose network — no local service is rendered."""

FILE_DATABASES = {"sqlite"}
"""Databases that live in a file inside the app container — no service either."""


def system_build_deps(db_type: str) -> list[str]:
    """Return the apt packages the builder stage needs for *db_type*."""
    return list(SYSTEM_BUILD_DEPS.get((db_type or "").lower(), []))


def db_label(db_type: str) -> str:
    """Return a human-readable name for *db_type*, for Dockerfile comments."""
    return DB_LABELS.get((db_type or "").lower(), db_type or "no database")


# ---------------------------------------------------------------------------
# Project state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectState:
    """Normalised snapshot of everything Docker rendering depends on."""

    project_name: str
    project_slug: str
    db_type: str = "sqlite"
    python_version: str = PYTHON_PATCH[DEFAULT_PYTHON]
    app_port: int = 8000
    cache: bool = False
    task: bool = False
    search: str = ""
    monitor: str = ""
    metrics: bool = False

    @property
    def needs_db_service(self) -> bool:
        """True when a database container belongs in the compose file."""
        db = self.db_type.lower()
        return bool(db) and db not in CLOUD_DATABASES and db not in FILE_DATABASES

    @property
    def needs_broker(self) -> bool:
        """True when Redis is needed — as a cache, a Celery broker, or both."""
        return self.cache or self.task


# ---------------------------------------------------------------------------
# Filesystem feature detection
#
# `kaira cache init` and friends predate the explicit flags in .kaira.json, so
# an existing project has the feature scaffolded but no flag recorded.  Reading
# both means Docker sync is correct for projects created before this phase.
# ---------------------------------------------------------------------------


def detect_cache(root: Path) -> bool:
    """True when Redis caching has been scaffolded in *root*."""
    return (root / "core" / "cache.py").is_file()


def detect_task(root: Path) -> bool:
    """True when Celery has been scaffolded in *root*."""
    return (root / "tasks" / "celery_app.py").is_file()


def detect_search(root: Path) -> str:
    """Return the integrated search provider name, or ``""`` if none."""
    search_dir = root / "integrations" / "search"
    if not search_dir.is_dir():
        return ""
    for provider in sorted(search_dir.iterdir()):
        if provider.is_dir() and (provider / "service.py").is_file():
            return provider.name
    return ""


def detect_monitor(root: Path) -> str:
    """Return the integrated monitoring provider name, or ``""`` if none."""
    monitor_dir = root / "integrations" / "monitor"
    if not monitor_dir.is_dir():
        return ""
    for provider in sorted(monitor_dir.iterdir()):
        if provider.is_dir() and (provider / "service.py").is_file():
            return provider.name
    return ""


def detect_metrics(root: Path) -> bool:
    """True when Kaira's own in-process metrics have been scaffolded in *root*.

    Distinct from :func:`detect_monitor`, which reports a *third-party* provider.
    A project can have either, both, or neither: ``kaira monitor init`` needs no
    account, and ``kaira integrate --provider monitor/sentry`` needs no metrics.
    """
    return (root / "core" / "metrics.py").is_file()


def slugify_project_name(name: str) -> str:
    """Return the Docker-safe project slug for *name*.

    Used for compose env-var defaults (``POSTGRES_DB``, volume names, …), which
    reject hyphens. The single source of truth: any caller that renders Docker
    templates — ``kaira docker init/sync`` via :func:`resolve_state`, and the
    project scaffold in ``commands/project.py`` — must compute the slug this
    same way, or a fresh project reports as drifted the moment ``docker sync``
    runs against it.
    """
    return name.lower().replace("-", "_").replace(" ", "_")


def resolve_state(
    root: Optional[Path] = None,
    *,
    python_version: Optional[str] = None,
) -> ProjectState:
    """Build the :class:`ProjectState` for the project rooted at *root*.

    Explicit ``.kaira.json`` flags win; filesystem detection fills the gaps for
    projects scaffolded before those flags existed.

    Args:
        root: Project root; defaults to the current working directory.
        python_version: Override for the base-image Python version.  Falls back
            to the value recorded in ``.kaira.json``, then to the default.

    Returns:
        The resolved project state.
    """
    from kaira.config import get_config

    root = Path.cwd() if root is None else root
    cfg = get_config()

    requested_python = python_version or getattr(cfg, "docker_python", "") or None

    return ProjectState(
        project_name=root.name,
        project_slug=slugify_project_name(root.name),
        db_type=(cfg.db_type or "sqlite").lower(),
        python_version=resolve_python_version(requested_python),
        app_port=8000,
        cache=bool(getattr(cfg, "cache_enabled", False)) or detect_cache(root),
        task=bool(getattr(cfg, "task_enabled", False)) or detect_task(root),
        search=(getattr(cfg, "search_provider", "") or detect_search(root)).lower(),
        monitor=(getattr(cfg, "monitor_provider", "") or detect_monitor(root)).lower(),
        metrics=bool(getattr(cfg, "monitor_metrics", False)) or detect_metrics(root),
    )


# ---------------------------------------------------------------------------
# Compose service registry
# ---------------------------------------------------------------------------

DEV = "dev"
PROD = "prod"

_LOGGING = {"max_size": "10m", "max_file": "3"}
"""Log rotation applied to every production service.

Without it the json-file driver grows without bound until the host disk fills —
the most common way a long-running compose deployment takes itself down.
"""


def _restart(env: str) -> str:
    return "always" if env == PROD else "unless-stopped"


def _env_file(env: str) -> str:
    return ".env.production" if env == PROD else ".env.development"


def _service(
    name: str,
    *,
    env: str,
    image: str = "",
    build: bool = False,
    command: Optional[list[str]] = None,
    environment: Optional[dict[str, str]] = None,
    env_file: Optional[str] = None,
    ports: Optional[list[str]] = None,
    volumes: Optional[list[str]] = None,
    depends_on: Optional[dict[str, str]] = None,
    healthcheck: Optional[dict[str, Any]] = None,
    read_only: bool = False,
    tmpfs: Optional[list[str]] = None,
    deploy: Optional[dict[str, str]] = None,
    volume_names: Optional[list[str]] = None,
    comment: str = "",
) -> dict[str, Any]:
    """Assemble one compose service block in the shape the macro renders.

    Centralising the shape here is what lets the templates stay a loop: every
    service — app, database, cache, worker, search — is the same dict, so the
    renderer never needs to know which feature produced it.
    """
    return {
        "name": name,
        "image": image,
        "build": build,
        "command": command,
        "environment": environment or {},
        "env_file": env_file,
        "ports": ports or [],
        "volumes": volumes or [],
        "depends_on": depends_on or {},
        "healthcheck": healthcheck,
        "restart": _restart(env),
        "read_only": read_only,
        "tmpfs": tmpfs or [],
        "logging": _LOGGING if env == PROD else None,
        "deploy": deploy,
        "volume_names": volume_names or [],
        "comment": comment,
    }


# --- app -------------------------------------------------------------------


def build_app(state: ProjectState, env: str) -> list[dict[str, Any]]:
    """Build the application service.

    Dev overrides ``CMD`` with ``--reload`` and bind-mounts the source tree;
    production keeps the Dockerfile's ``CMD`` and adds resource limits.
    """
    depends: dict[str, str] = {}
    if state.needs_db_service:
        depends["db"] = "service_healthy"
    if state.needs_broker:
        depends["redis"] = "service_healthy"
    if state.search in SEARCH_IMAGES:
        depends["search"] = "service_healthy"

    volumes: list[str] = []
    command: Optional[list[str]] = None
    if env == DEV:
        # Bind-mount for live reload.  The anonymous volume on .venv stops a
        # host virtualenv from shadowing the container's installed packages.
        volumes = [".:/app", "/app/.venv"]
        command = [
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",  # nosec B104 - binds inside the container network namespace,
            # not the host; the container's own port isolation is what makes this
            # reachable at all via the compose port mapping.
            "--port",
            str(state.app_port),
            "--reload",
        ]

    deploy = {"memory": "512M", "cpus": "0.5"} if env == PROD else None

    return [
        _service(
            "app",
            env=env,
            build=True,
            command=command,
            env_file=_env_file(env),
            ports=[f"{state.app_port}:{state.app_port}"],
            volumes=volumes,
            depends_on=depends,
            healthcheck={
                "test": [
                    "CMD",
                    "python",
                    "-c",
                    "import urllib.request,sys;"
                    f"sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:{state.app_port}/health',"
                    " timeout=2).status == 200 else 1)",
                ],
                "interval": "30s",
                "timeout": "5s",
                "retries": 3,
                "start_period": "15s",
            },
            # A read-only root filesystem plus a small tmpfs: Python still needs
            # a writable /tmp for temp files and matplotlib-style caches.
            read_only=True,
            tmpfs=["/tmp:size=64m"],  # nosec B108 - a compose tmpfs mount spec,
            # not a path the app writes to directly; size-capped and wiped on
            # container stop by design.
            deploy=deploy,
            comment="FastAPI application",
        )
    ]


# --- database --------------------------------------------------------------

DATABASE_IMAGES: dict[str, dict[str, Any]] = {
    "postgresql": {
        "image": "postgres:16.4-alpine",
        "port": "5432",
        "volume": "pgdata",
        "data_dir": "/var/lib/postgresql/data",
        "environment": {
            "POSTGRES_USER": "${POSTGRES_USER:-kaira}",
            "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:-kaira}",
            "POSTGRES_DB": "${POSTGRES_DB:-%(slug)s}",
        },
        "healthcheck": ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-kaira}"],
    },
    "mysql": {
        "image": "mysql:8.4.3",
        "port": "3306",
        "volume": "mysqldata",
        "data_dir": "/var/lib/mysql",
        "environment": {
            "MYSQL_ROOT_PASSWORD": "${MYSQL_ROOT_PASSWORD:-kaira}",
            "MYSQL_USER": "${MYSQL_USER:-kaira}",
            "MYSQL_PASSWORD": "${MYSQL_PASSWORD:-kaira}",
            "MYSQL_DATABASE": "${MYSQL_DATABASE:-%(slug)s}",
        },
        "healthcheck": ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1"],
    },
    "mongodb": {
        "image": "mongo:7.0.14",
        "port": "27017",
        "volume": "mongodata",
        "data_dir": "/data/db",
        "environment": {
            "MONGO_INITDB_ROOT_USERNAME": "${MONGO_USER:-kaira}",
            "MONGO_INITDB_ROOT_PASSWORD": "${MONGO_PASSWORD:-kaira}",
            "MONGO_INITDB_DATABASE": "${MONGO_DB:-%(slug)s}",
        },
        "healthcheck": [
            "CMD",
            "mongosh",
            "--quiet",
            "--eval",
            "db.adminCommand('ping')",
        ],
    },
}
"""``db_type`` → container spec.  Aliases are normalised in :func:`build_database`."""

_DB_ALIASES = {"postgres": "postgresql", "mariadb": "mysql"}


def build_database(state: ProjectState, env: str) -> list[dict[str, Any]]:
    """Build the database service, or nothing for cloud/file databases."""
    db = _DB_ALIASES.get(state.db_type, state.db_type)
    spec = DATABASE_IMAGES.get(db)
    if spec is None or not state.needs_db_service:
        return []

    environment = {
        key: value % {"slug": state.project_slug} if "%(slug)s" in value else value
        for key, value in spec["environment"].items()
    }

    # The port is published in dev so local tooling (psql, Compass, a GUI) can
    # reach it.  In production the database stays on the compose network only.
    ports = [f"{spec['port']}:{spec['port']}"] if env == DEV else []

    return [
        _service(
            "db",
            env=env,
            image=spec["image"],
            environment=environment,
            env_file=_env_file(env),
            ports=ports,
            volumes=[f"{spec['volume']}:{spec['data_dir']}"],
            healthcheck={
                "test": spec["healthcheck"],
                "interval": "10s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "10s",
            },
            volume_names=[spec["volume"]],
            comment=f"{db_label(db)} database",
        )
    ]


# --- redis (cache and/or Celery broker) ------------------------------------

REDIS_IMAGE = "redis:7.4.1-alpine"


def build_redis(state: ProjectState, env: str) -> list[dict[str, Any]]:
    """Build the Redis service when caching or Celery is enabled.

    One service covers both roles — a project with cache *and* tasks gets a
    single Redis, not two.
    """
    if not state.needs_broker:
        return []

    roles = [
        r for r, on in (("cache", state.cache), ("Celery broker", state.task)) if on
    ]
    ports = ["6379:6379"] if env == DEV else []

    return [
        _service(
            "redis",
            env=env,
            image=REDIS_IMAGE,
            command=["redis-server", "--appendonly", "yes"],
            ports=ports,
            volumes=["redisdata:/data"],
            healthcheck={
                "test": ["CMD", "redis-cli", "ping"],
                "interval": "10s",
                "timeout": "3s",
                "retries": 5,
            },
            volume_names=["redisdata"],
            comment=f"Redis — {' + '.join(roles)}",
        )
    ]


# --- celery worker ---------------------------------------------------------


def build_worker(state: ProjectState, env: str) -> list[dict[str, Any]]:
    """Build the Celery worker service when background tasks are enabled.

    Reuses the application image — the worker runs the same code with a
    different entrypoint, so there is nothing extra to build.
    """
    if not state.task:
        return []

    depends = {"redis": "service_healthy"}
    if state.needs_db_service:
        depends["db"] = "service_healthy"

    volumes = [".:/app", "/app/.venv"] if env == DEV else []
    deploy = {"memory": "512M", "cpus": "0.5"} if env == PROD else None

    return [
        _service(
            "worker",
            env=env,
            build=True,
            command=[
                "celery",
                "-A",
                "tasks.celery_app",
                "worker",
                "--loglevel=info",
            ],
            env_file=_env_file(env),
            volumes=volumes,
            depends_on=depends,
            healthcheck={
                "test": ["CMD", "celery", "-A", "tasks.celery_app", "status"],
                "interval": "30s",
                "timeout": "10s",
                "retries": 3,
                "start_period": "20s",
            },
            read_only=True,
            tmpfs=["/tmp:size=64m"],  # nosec B108 - a compose tmpfs mount spec,
            # not a path the app writes to directly; size-capped and wiped on
            # container stop by design.
            deploy=deploy,
            comment="Celery background worker",
        )
    ]


# --- search ----------------------------------------------------------------

SEARCH_IMAGES: dict[str, dict[str, Any]] = {
    "elasticsearch": {
        "image": "docker.elastic.co/elasticsearch/elasticsearch:8.15.3",
        "port": "9200",
        "volume": "esdata",
        "data_dir": "/usr/share/elasticsearch/data",
        "environment": {
            "discovery.type": "single-node",
            "xpack.security.enabled": "false",
            "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
        },
        "healthcheck": [
            "CMD-SHELL",
            "curl -fsS http://localhost:9200/_cluster/health || exit 1",
        ],
    },
    "meilisearch": {
        "image": "getmeili/meilisearch:v1.11.1",
        "port": "7700",
        "volume": "meilidata",
        "data_dir": "/meili_data",
        "environment": {
            "MEILI_MASTER_KEY": "${MEILISEARCH_API_KEY:-kaira_dev_master_key}",
            "MEILI_ENV": "development",
        },
        "healthcheck": [
            "CMD-SHELL",
            "curl -fsS http://localhost:7700/health || exit 1",
        ],
    },
}


def build_search(state: ProjectState, env: str) -> list[dict[str, Any]]:
    """Build the search service when a search provider is integrated."""
    spec = SEARCH_IMAGES.get(state.search)
    if spec is None:
        return []

    environment = dict(spec["environment"])
    if state.search == "meilisearch" and env == PROD:
        environment["MEILI_ENV"] = "production"

    ports = [f"{spec['port']}:{spec['port']}"] if env == DEV else []

    return [
        _service(
            "search",
            env=env,
            image=spec["image"],
            environment=environment,
            ports=ports,
            volumes=[f"{spec['volume']}:{spec['data_dir']}"],
            healthcheck={
                "test": spec["healthcheck"],
                "interval": "15s",
                "timeout": "5s",
                "retries": 5,
                "start_period": "30s",
            },
            volume_names=[spec["volume"]],
            comment=f"{state.search.capitalize()} search engine",
        )
    ]


# --- registry --------------------------------------------------------------


@dataclass(frozen=True)
class ServiceDefinition:
    """One pluggable compose service family.

    Attributes:
        key: Stable identifier, used in status output and tests.
        build: ``(state, env) -> list[service dict]``.  Returns an empty list
            when the feature is not enabled, so enablement and rendering live
            in one place.
    """

    key: str
    build: Callable[[ProjectState, str], list[dict[str, Any]]]


SERVICE_REGISTRY: list[ServiceDefinition] = [
    ServiceDefinition("app", build_app),
    ServiceDefinition("database", build_database),
    ServiceDefinition("cache", build_redis),
    ServiceDefinition("task", build_worker),
    ServiceDefinition("search", build_search),
]
"""The full set of service families Docker knows how to render.

Adding a feature in a future phase means appending one entry here and — only if
the new service needs a compose key the macro does not already emit — extending
``_docker_macros.j2``.  Neither compose template changes.
"""


def build_services(state: ProjectState, env: str) -> list[dict[str, Any]]:
    """Return every enabled compose service for *state* in *env*.

    Args:
        state: Resolved project state.
        env: ``"dev"`` or ``"prod"``.

    Returns:
        Service dicts in registry order, ready for the compose macro.
    """
    services: list[dict[str, Any]] = []
    for definition in SERVICE_REGISTRY:
        services.extend(definition.build(state, env))
    return services


def collect_volume_names(services: list[dict[str, Any]]) -> list[str]:
    """Return the named volumes declared by *services*, de-duplicated in order."""
    seen: list[str] = []
    for svc in services:
        for name in svc["volume_names"]:
            if name not in seen:
                seen.append(name)
    return seen


def enabled_features(state: ProjectState) -> list[str]:
    """Return human-readable names of the features driving Docker rendering."""
    features: list[str] = [db_label(state.db_type)]
    if state.cache:
        features.append("cache (Redis)")
    if state.task:
        features.append("tasks (Celery)")
    if state.search:
        features.append(f"search ({state.search})")
    if state.metrics:
        features.append("metrics (/metrics)")
    if state.monitor:
        features.append(f"monitoring ({state.monitor})")
    return features


# ---------------------------------------------------------------------------
# Template context
# ---------------------------------------------------------------------------


@dataclass
class DockerContext:
    """Everything the four Docker templates render from."""

    state: ProjectState
    env: str
    services: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return the Jinja context mapping."""
        return {
            "project_name": self.state.project_name,
            "project_slug": self.state.project_slug,
            "db_type": self.state.db_type,
            "db_label": db_label(self.state.db_type),
            "python_version": self.state.python_version,
            "app_port": self.state.app_port,
            "system_deps": system_build_deps(self.state.db_type),
            "cache": self.state.cache,
            "task": self.state.task,
            "search": self.state.search,
            "monitor": self.state.monitor,
            "metrics": self.state.metrics,
            "env": self.env,
            "env_file": _env_file(self.env),
            "services": self.services,
            "volume_names": collect_volume_names(self.services),
        }


def build_context(state: ProjectState, env: str) -> dict[str, Any]:
    """Return the Jinja context for *state* rendered for *env*."""
    return DockerContext(state, env, build_services(state, env)).as_dict()
