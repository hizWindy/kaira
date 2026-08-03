"""Tests for route discovery and docs generation.

The behaviour under test: ``kaira docs generate`` documents every router the
project actually exposes — including hand-written ones that no model backs —
rather than only the models tracked in ``.kaira.json``.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from kaira.core.route_discovery import (
    Endpoint,
    RouteGroup,
    _endpoints_from_spec,
    _group_endpoints,
    discover_routes,
)
from kaira.main import app

runner = CliRunner()


CUSTOM_ROUTER = '''
"""Hand-written analytics router — backed by no model."""

from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", summary="Dashboard summary")
async def summary(current_user: dict = Depends(get_current_user)) -> dict:
    """Return aggregate counts."""
    return {}


@router.post("/report")
async def report() -> dict:
    """Queue a report build."""
    return {}


@router.get("/internal", include_in_schema=False)
async def internal() -> dict:
    """Hidden from the schema on purpose."""
    return {}
'''

GENERATED_ROUTER = '''
"""Generated CRUD router for Widget."""

from fastapi import APIRouter, Depends

router = APIRouter(prefix="/widgets", tags=["Widget"])


@router.post("/", summary="Create Widget")
async def create_widget() -> dict:
    """Create a widget."""
    return {}


@router.get("/list", summary="List Widgets")
@router.get("/", summary="List Widgets", include_in_schema=False)
async def list_widgets() -> dict:
    """List widgets."""
    return {}
'''

MAIN_PY = '''
"""App entry point."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/health", tags=["HealthCheck"])
def health_check() -> dict:
    """Return API health status."""
    return {"status": "ok"}
'''


def _make_project(tmp_path: Path) -> None:
    """Write a project tree with one generated and one custom router."""
    (tmp_path / ".kaira.json").write_text(
        json.dumps(
            {
                "db_type": "sqlite",
                "api_version": "v1",
                "generated_models": [
                    {
                        "name": "Widget",
                        "fields": [{"name": "label", "type": "str"}],
                        "relations": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    routers = tmp_path / "routers"
    routers.mkdir()
    (routers / "__init__.py").touch()
    (routers / "analytics_router.py").write_text(CUSTOM_ROUTER, encoding="utf-8")
    (routers / "widget_router.py").write_text(GENERATED_ROUTER, encoding="utf-8")
    (tmp_path / "main.py").write_text(MAIN_PY, encoding="utf-8")


# ── Source scanning ──────────────────────────────────────────────────────────


def test_source_scan_finds_custom_router(tmp_path):
    """A hand-written router is discovered even though no model backs it."""
    _make_project(tmp_path)

    groups, strategy = discover_routes(
        tmp_path, {"Widget"}, prefer_live=False, api_prefix="/api/v1"
    )
    assert strategy == "source"

    by_name = {g.name: g for g in groups}
    assert "Analytics" in by_name, f"custom router missing; found {list(by_name)}"

    analytics = by_name["Analytics"]
    assert analytics.is_custom
    assert analytics.source_file == "routers/analytics_router.py"
    assert {e.signature() for e in analytics.endpoints} == {
        "GET /api/v1/analytics/summary",
        "POST /api/v1/analytics/report",
    }


def test_include_in_schema_false_is_excluded(tmp_path):
    """Routes hidden from the schema stay out of the docs."""
    _make_project(tmp_path)
    groups, _ = discover_routes(tmp_path, {"Widget"}, prefer_live=False)
    paths = {e.path for g in groups for e in g.endpoints}
    assert not any("internal" in p for p in paths)


def test_stacked_decorators_are_both_captured(tmp_path):
    """One handler with two route decorators yields two endpoints."""
    _make_project(tmp_path)
    groups, _ = discover_routes(
        tmp_path, {"Widget"}, prefer_live=False, api_prefix="/api/v1"
    )
    widget = next(g for g in groups if g.name == "Widget")
    signatures = {e.signature() for e in widget.endpoints}
    # The second decorator sets include_in_schema=False, so only /list survives.
    assert "GET /api/v1/widgets/list" in signatures
    # Trailing slash preserved: prefix "/widgets" + route "/" is what FastAPI
    # registers, and what the live schema reports.
    assert "POST /api/v1/widgets/" in signatures


def test_groups_are_classified_by_kind(tmp_path):
    """model / system / custom must not be conflated."""
    _make_project(tmp_path)
    groups, _ = discover_routes(tmp_path, {"Widget"}, prefer_live=False)
    kinds = {g.name: g.kind for g in groups}
    assert kinds["Widget"] == "model"
    assert kinds["Analytics"] == "custom"
    assert kinds["HealthCheck"] == "system"


def test_auth_dependency_is_detected(tmp_path):
    """Endpoints guarded by get_current_user are marked as requiring auth."""
    _make_project(tmp_path)
    groups, _ = discover_routes(tmp_path, {"Widget"}, prefer_live=False)
    analytics = next(g for g in groups if g.name == "Analytics")
    by_path = {e.path.split("/")[-1]: e for e in analytics.endpoints}
    assert by_path["summary"].auth_required
    assert not by_path["report"].auth_required


def test_api_prefix_applied_to_routers_not_main(tmp_path):
    """Routers mount under the version prefix; app-level routes do not."""
    _make_project(tmp_path)
    groups, _ = discover_routes(
        tmp_path, {"Widget"}, prefer_live=False, api_prefix="/api/v1"
    )
    paths = {e.path for g in groups for e in g.endpoints}
    assert "/api/v1/analytics/summary" in paths
    assert "/health" in paths, "main.py routes must not gain the version prefix"


# ── OpenAPI parsing ──────────────────────────────────────────────────────────


def test_openapi_spec_parsing():
    """Endpoints, tags, auth and models are read out of an OpenAPI schema."""
    spec = {
        "paths": {
            "/api/v1/analytics/summary": {
                "get": {
                    "summary": "Dashboard summary",
                    "tags": ["Analytics"],
                    "security": [{"OAuth2PasswordBearer": []}],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Summary"}
                                }
                            }
                        }
                    },
                }
            },
            "/docs": {"get": {"summary": "Swagger"}},
        }
    }
    endpoints = _endpoints_from_spec(spec)
    assert len(endpoints) == 1, "the docs UI path must be excluded"

    endpoint = endpoints[0]
    assert endpoint.method == "GET"
    assert endpoint.tags == ["Analytics"]
    assert endpoint.auth_required
    assert endpoint.response_model == "Summary"


def test_list_response_model_is_unwrapped():
    """An array response reports the element type, not a bare 'array'."""
    spec = {
        "paths": {
            "/api/v1/widgets/list": {
                "get": {
                    "tags": ["Widget"],
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/WidgetResponse"
                                        },
                                    }
                                }
                            }
                        }
                    },
                }
            }
        }
    }
    (endpoint,) = _endpoints_from_spec(spec)
    assert endpoint.response_model == "list[WidgetResponse]"


def test_untagged_endpoints_group_by_path_not_version():
    """Without tags, the group name comes from the resource, not 'api' or 'v1'."""
    endpoints = [Endpoint(method="GET", path="/api/v1/reports/daily")]
    (group,) = _group_endpoints(endpoints, set())
    assert group.name == "Reports"


# ── docs generate ────────────────────────────────────────────────────────────


def test_docs_generate_includes_custom_router(tmp_path, monkeypatch):
    """The reported gap: a custom router must appear in the generated docs."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _make_project(tmp_path)

    result = runner.invoke(app, ["docs", "generate", "--source"])
    assert result.exit_code == 0

    doc = (tmp_path / "docs" / "api.md").read_text(encoding="utf-8")
    assert "## Analytics" in doc, "custom router absent from docs"
    assert "/api/v1/analytics/summary" in doc
    assert "custom router" in doc
    # Generated CRUD is still documented alongside it.
    assert "## Widget" in doc
    assert "| `label` | `str` | Yes |" in doc


def test_docs_generate_documents_real_endpoints_only(tmp_path, monkeypatch):
    """Docs reflect declared routes, not an assumed 5-endpoint CRUD shape."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _make_project(tmp_path)

    assert runner.invoke(app, ["docs", "generate", "--source"]).exit_code == 0
    doc = (tmp_path / "docs" / "api.md").read_text(encoding="utf-8")

    # Widget declares no delete route, so none may be documented.
    assert "DELETE" not in doc
    assert "/widgets/{id}" not in doc, "placeholder path from the old template"


def test_docs_generate_custom_only_filter(tmp_path, monkeypatch):
    """--custom narrows output to hand-written routers."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _make_project(tmp_path)

    assert runner.invoke(app, ["docs", "generate", "--custom", "--source"]).exit_code == 0
    doc = (tmp_path / "docs" / "api.md").read_text(encoding="utf-8")
    assert "## Analytics" in doc
    assert "## Widget" not in doc


def test_docs_generate_single_section(tmp_path, monkeypatch):
    """Naming a section writes just that section to its own file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _make_project(tmp_path)

    assert runner.invoke(
        app, ["docs", "generate", "Analytics", "--source"]
    ).exit_code == 0
    assert (tmp_path / "docs" / "Analytics.md").exists()


def test_docs_generate_unknown_section_lists_options(tmp_path, monkeypatch):
    """An unknown name fails with the available sections, not a bare error."""
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path)

    result = runner.invoke(app, ["docs", "generate", "Nope", "--source"])
    assert result.exit_code == 1
    assert "Analytics" in result.output


def test_route_group_kind_helpers():
    """is_custom is true only for developer-written routers."""
    assert RouteGroup(name="X", kind="custom").is_custom
    assert not RouteGroup(name="X", kind="system").is_custom
    assert not RouteGroup(name="X", kind="model").is_custom
    assert RouteGroup(name="X", kind="model").is_model_backed
