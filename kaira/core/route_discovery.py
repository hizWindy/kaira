"""Discover every route actually exposed by a generated project.

``.kaira.json`` only tracks models Kaira generated, so anything hand-written —
a dashboard router, an AI endpoint, a webhook receiver — is invisible to it.
Documentation built from that snapshot silently omits half the API.

Two strategies, best first:

``openapi``
    Import the project's ``main.app`` in its own interpreter and read
    ``app.openapi()``. This is ground truth: it includes custom routers, auth
    routes, and anything mounted at runtime, with the real paths, summaries and
    security requirements.

``source``
    Parse ``routers/*.py`` and ``main.py`` with :mod:`ast`. Used when the app
    cannot be imported (dependencies missing, import-time error). Less precise
    — it cannot resolve a prefix built from a variable — but needs nothing
    installed and never executes project code.
"""

from __future__ import annotations

import ast
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# Paths FastAPI serves for the docs UI itself — never part of the documented API.
_DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# Groups Kaira scaffolds itself. They belong in the docs, but calling them
# "custom" would be wrong — custom must mean "the developer wrote this".
_SYSTEM_GROUPS = {
    "auth",
    "authentication",
    "healthcheck",
    "health",
    "root",
    "websocket",
}
_SYSTEM_SOURCES = {"auth/router.py", "main.py"}


@dataclass
class Endpoint:
    """One HTTP operation exposed by the API."""

    method: str
    path: str
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    auth_required: bool = False
    request_model: str = ""
    response_model: str = ""

    def signature(self) -> str:
        """``GET /api/v1/users/{uuid}`` — stable identity for sorting/dedup."""
        return f"{self.method} {self.path}"


@dataclass
class RouteGroup:
    """A set of endpoints that belong together — one router, or one tag.

    ``kind`` separates three things that must not be conflated in docs:
    ``model`` (generated CRUD for a tracked model), ``system`` (auth, health,
    root — scaffolded by Kaira), and ``custom`` (hand-written by the developer).
    """

    name: str
    endpoints: list[Endpoint] = field(default_factory=list)
    prefix: str = ""
    source_file: str = ""
    kind: str = "custom"

    @property
    def is_model_backed(self) -> bool:
        """True when this group is the CRUD surface of a tracked model."""
        return self.kind == "model"

    @property
    def is_custom(self) -> bool:
        """True only for routers the developer wrote themselves."""
        return self.kind == "custom"


# ---------------------------------------------------------------------------
# Strategy 1 — live OpenAPI schema
# ---------------------------------------------------------------------------

_DUMP_SCRIPT = """
import json, sys
sys.path.insert(0, {root!r})
import main
spec = main.app.openapi()
with open({out!r}, "w", encoding="utf-8") as fh:
    json.dump(spec, fh)
"""


def load_openapi_spec(project_root: Path) -> dict | None:
    """Return the project's OpenAPI schema, or ``None`` if it cannot be built.

    Runs in the project's own interpreter so its dependencies resolve. The
    schema is written to a temp file rather than stdout because importing the
    app also emits log lines, which would corrupt a piped JSON payload.
    """
    if not (project_root / "main.py").exists():
        return None

    from kaira.core.project_runner import run_project_script

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "openapi.json"
        code = _DUMP_SCRIPT.format(root=str(project_root), out=str(out))
        try:
            result = run_project_script(code, project_root)
        except Exception:
            return None
        if result.returncode != 0 or not out.exists():
            return None
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None


def _ref_name(schema: dict | None) -> str:
    """Extract a component name from a ``$ref``/array-of-``$ref`` schema node."""
    if not isinstance(schema, dict):
        return ""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        inner = _ref_name(schema.get("items"))
        return f"list[{inner}]" if inner else ""
    return ""


def _endpoints_from_spec(spec: dict) -> list[Endpoint]:
    """Flatten an OpenAPI paths object into :class:`Endpoint` records."""
    endpoints: list[Endpoint] = []
    for path, item in (spec.get("paths") or {}).items():
        if path in _DOC_PATHS:
            continue
        for method, op in (item or {}).items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue

            body = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            ok = op.get("responses", {}).get("200") or op.get("responses", {}).get(
                "201"
            )
            resp = (
                (ok or {}).get("content", {}).get("application/json", {}).get("schema")
            )

            endpoints.append(
                Endpoint(
                    method=method.upper(),
                    path=path,
                    summary=op.get("summary", ""),
                    description=op.get("description", ""),
                    tags=list(op.get("tags") or []),
                    # A non-empty security list means the operation is guarded.
                    auth_required=bool(op.get("security")),
                    request_model=_ref_name(body),
                    response_model=_ref_name(resp),
                )
            )
    return endpoints


# ---------------------------------------------------------------------------
# Strategy 2 — AST scan of the source tree
# ---------------------------------------------------------------------------


def _literal(node: ast.expr | None) -> object | None:
    """Best-effort literal evaluation; ``None`` for anything dynamic."""
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def _router_metadata(tree: ast.Module) -> tuple[str, list[str]]:
    """Return ``(prefix, tags)`` from an ``APIRouter(...)`` assignment."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else ""
        )
        if name != "APIRouter":
            continue
        prefix, tags = "", []
        for kw in node.value.keywords:
            if kw.arg == "prefix":
                prefix = _literal(kw.value) or ""
            elif kw.arg == "tags":
                tags = [str(t) for t in (_literal(kw.value) or [])]
        return str(prefix), tags
    return "", []


def _decorator_endpoints(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    prefix: str,
    router_tags: list[str],
) -> list[Endpoint]:
    """Read every route decorator stacked on one handler.

    A handler may carry more than one decorator — Kaira's own list endpoint
    registers both ``/`` and ``/list`` — so each is emitted separately.
    """
    found: list[Endpoint] = []
    doc = ast.get_docstring(node) or ""

    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        method = dec.func.attr.lower()
        if method not in HTTP_METHODS:
            continue

        route = _literal(dec.args[0]) if dec.args else ""
        if not isinstance(route, str):
            continue

        options = {kw.arg: kw.value for kw in dec.keywords}
        if _literal(options.get("include_in_schema")) is False:
            continue

        # A handler's docstring is the same text FastAPI would surface, so it
        # is the right fallback when the decorator carries no explicit summary.
        first_line = doc.strip().split("\n")[0] if doc else ""
        summary = _literal(options.get("summary")) or first_line
        description = _literal(options.get("description")) or ""
        tags = [str(t) for t in (_literal(options.get("tags")) or [])] or router_tags

        response_model = ""
        if "response_model" in options:
            try:
                response_model = ast.unparse(options["response_model"])
            except Exception:
                response_model = ""

        # Kept verbatim: FastAPI registers prefix "/widgets" + route "/" as
        # "/widgets/", trailing slash included. Normalising it here would make
        # the source scan disagree with the live schema for the same route.
        full = (prefix + route) or "/"

        found.append(
            Endpoint(
                method=method.upper(),
                path=full,
                summary=str(summary),
                description=str(description) or first_line,
                tags=tags,
                auth_required=_has_auth_dependency(node),
                response_model=response_model,
            )
        )
    return found


def _has_auth_dependency(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Detect a ``Depends(get_current_user)``-style guard in the signature."""
    for arg in list(node.args.args) + list(node.args.kwonlyargs):
        if arg.annotation is not None:
            try:
                if "get_current_user" in ast.unparse(arg.annotation):
                    return True
            except Exception:
                pass
    for default in list(node.args.defaults) + list(node.args.kw_defaults):
        if default is None:
            continue
        try:
            if "get_current_user" in ast.unparse(default):
                return True
        except Exception:
            continue
    return False


def _scan_router_file(path: Path) -> tuple[str, list[str], list[Endpoint]]:
    """Parse one router module into ``(prefix, tags, endpoints)``."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return "", [], []

    prefix, tags = _router_metadata(tree)
    endpoints: list[Endpoint] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            endpoints.extend(_decorator_endpoints(node, prefix, tags))
    return prefix, tags, endpoints


def _scan_main(path: Path) -> list[Endpoint]:
    """Read routes declared directly on the app in ``main.py`` (root, health)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    endpoints: list[Endpoint] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            endpoints.extend(_decorator_endpoints(node, "", []))
    return endpoints


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def _group_name(endpoint: Endpoint, fallback: str) -> str:
    """Prefer the operation's tag; fall back to the router/module name."""
    return endpoint.tags[0] if endpoint.tags else fallback


def _group_endpoints(
    endpoints: list[Endpoint],
    model_names: set[str],
    source_by_name: dict[str, str] | None = None,
) -> list[RouteGroup]:
    """Bucket endpoints into groups and mark which are model-backed."""
    source_by_name = source_by_name or {}
    buckets: dict[str, list[Endpoint]] = {}

    for endpoint in endpoints:
        segments = [s for s in endpoint.path.split("/") if s and not s.startswith("{")]
        # Skip the /api/<version> prefix when deriving a name from the path.
        tail = [s for s in segments if s != "api" and not _looks_like_version(s)]
        fallback = (
            tail[0].replace("_", " ").title().replace(" ", "") if tail else "Root"
        )
        buckets.setdefault(_group_name(endpoint, fallback), []).append(endpoint)

    groups: list[RouteGroup] = []
    for name, items in sorted(buckets.items()):
        items.sort(key=Endpoint.signature)
        prefixes = {e.path.rsplit("/", 1)[0] for e in items}
        source = source_by_name.get(name, "")

        if name in model_names:
            kind = "model"
        elif name.lower() in _SYSTEM_GROUPS or source in _SYSTEM_SOURCES:
            kind = "system"
        else:
            kind = "custom"

        groups.append(
            RouteGroup(
                name=name,
                endpoints=items,
                prefix=min(prefixes, key=len) if prefixes else "",
                source_file=source,
                kind=kind,
            )
        )
    return groups


def _looks_like_version(segment: str) -> bool:
    """True for ``v1``, ``v2``… so the version prefix never names a group."""
    return len(segment) >= 2 and segment[0] == "v" and segment[1:].isdigit()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def discover_routes(
    project_root: Path,
    model_names: set[str] | None = None,
    *,
    prefer_live: bool = True,
    api_prefix: str = "",
) -> tuple[list[RouteGroup], str]:
    """Discover every route group in the project.

    Args:
        project_root: Project root containing ``main.py`` and ``routers/``.
        model_names: Tracked model names, used to mark groups as model-backed
            so custom routers can be told apart from generated CRUD.
        prefer_live: Try the live OpenAPI schema first. Set False to force the
            source scan (no project code is executed).
        api_prefix: Version prefix routers are mounted under (``/api/v1``).
            Applied only in source mode — the live schema already has it baked
            into every path.

    Returns:
        ``(groups, strategy)`` where strategy is ``"openapi"`` or ``"source"``.
        An empty list means nothing could be discovered by either route.
    """
    model_names = model_names or set()

    if prefer_live:
        spec = load_openapi_spec(project_root)
        if spec:
            endpoints = _endpoints_from_spec(spec)
            if endpoints:
                return _group_endpoints(endpoints, model_names), "openapi"

    endpoints: list[Endpoint] = []
    source_by_name: dict[str, str] = {}

    # Routers are mounted under the version prefix; routes declared directly on
    # the app in main.py are not, so the prefix is applied per-source.
    def _collect(path: Path, source: str, fallback: str) -> None:
        _prefix, _tags, found = _scan_router_file(path)
        for endpoint in found:
            if api_prefix:
                endpoint.path = api_prefix.rstrip("/") + endpoint.path
            source_by_name.setdefault(_group_name(endpoint, fallback), source)
        endpoints.extend(found)

    routers_dir = project_root / "routers"
    if routers_dir.is_dir():
        for router_file in sorted(routers_dir.glob("*.py")):
            if router_file.name == "__init__.py":
                continue
            _collect(router_file, f"routers/{router_file.name}", router_file.stem)

    # Auth lives outside routers/ but is very much part of the API.
    auth_router = project_root / "auth" / "router.py"
    if auth_router.exists():
        _collect(auth_router, "auth/router.py", "Auth")

    main_file = project_root / "main.py"
    if main_file.exists():
        for endpoint in _scan_main(main_file):
            source_by_name.setdefault(_group_name(endpoint, "Root"), "main.py")
            endpoints.append(endpoint)

    return _group_endpoints(endpoints, model_names, source_by_name), "source"
