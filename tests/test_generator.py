"""Tests for devflow.core.generator."""

from __future__ import annotations

import pytest

from devflow.config import DevFlowConfig
from devflow.core.parser import parse_fields, parse_relation
from devflow.core.generator import (
    generate_layer,
    generate_all,
    resolve_output_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> DevFlowConfig:
    return DevFlowConfig()


@pytest.fixture
def simple_fields():
    return parse_fields("username:str, email:str, age:int")


@pytest.fixture
def optional_fields():
    return parse_fields("title:str, body:Optional[str], published:bool")


@pytest.fixture
def relations():
    return [parse_relation("one-to-many", "Comment", cascade="all, delete-orphan")]


# ---------------------------------------------------------------------------
# generate_layer — model
# ---------------------------------------------------------------------------

class TestGenerateModel:
    def test_class_name_in_output(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert "class User(Base):" in output

    def test_table_name_in_output(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert '__tablename__ = "users"' in output

    def test_fields_present(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert "username" in output
        assert "email" in output
        assert "age" in output

    def test_sqlalchemy_types(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert "String" in output
        assert "Integer" in output

    def test_id_column_always_present(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert "primary_key=True" in output

    def test_timestamps_present(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert "created_at" in output
        assert "updated_at" in output

    def test_repr_present(self, config, simple_fields):
        output = generate_layer("model", "User", simple_fields, [], config)
        assert "__repr__" in output

    def test_optional_field_nullable(self, config, optional_fields):
        output = generate_layer("model", "Post", optional_fields, [], config)
        assert "nullable=True" in output

    def test_compound_model_name(self, config, simple_fields):
        output = generate_layer("model", "BlogPost", simple_fields, [], config)
        assert "class BlogPost(Base):" in output
        assert '__tablename__ = "blog_posts"' in output

    def test_one_to_many_relation(self, config, simple_fields, relations):
        output = generate_layer("model", "Post", simple_fields, relations, config)
        assert "relationship" in output
        assert "Comment" in output


# ---------------------------------------------------------------------------
# generate_layer — schema
# ---------------------------------------------------------------------------

class TestGenerateSchema:
    def test_base_schema(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        assert "class UserBase(BaseModel):" in output

    def test_create_schema(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        assert "class UserCreate(UserBase):" in output

    def test_update_schema(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        assert "class UserUpdate(BaseModel):" in output

    def test_response_schema(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        assert "class UserResponse(BaseModel):" in output

    def test_config_dict(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        assert "from_attributes=True" in output

    def test_response_has_id_and_timestamps(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        assert "uuid: str" in output
        assert "created_at" in output
        assert "updated_at" in output

    def test_update_fields_optional(self, config, simple_fields):
        output = generate_layer("schema", "User", simple_fields, [], config)
        # Update schema should have Optional or = None for all fields
        lines = output.splitlines()
        in_update = False
        update_field_lines = []
        for line in lines:
            if "class UserUpdate" in line:
                in_update = True
            elif in_update and line.startswith("class "):
                in_update = False
            elif in_update and ":" in line and "pass" not in line and "model_config" not in line:
                update_field_lines.append(line)
        for line in update_field_lines:
            assert "None" in line or "Optional" in line, f"Expected optional field: {line}"


# ---------------------------------------------------------------------------
# generate_layer — repository
# ---------------------------------------------------------------------------

class TestGenerateRepository:
    def test_class_name(self, config, simple_fields):
        output = generate_layer("repository", "User", simple_fields, [], config)
        assert "class UserRepository:" in output

    def test_crud_methods(self, config, simple_fields):
        output = generate_layer("repository", "User", simple_fields, [], config)
        assert "def create(" in output
        assert "def get_by_id(" in output
        assert "def get_all(" in output
        assert "def update(" in output
        assert "def delete(" in output

    def test_session_injection(self, config, simple_fields):
        output = generate_layer("repository", "User", simple_fields, [], config)
        assert "Session" in output
        assert "self.db" in output


# ---------------------------------------------------------------------------
# generate_layer — service
# ---------------------------------------------------------------------------

class TestGenerateService:
    def test_class_name(self, config, simple_fields):
        output = generate_layer("service", "User", simple_fields, [], config)
        assert "class UserService:" in output

    def test_repository_usage(self, config, simple_fields):
        output = generate_layer("service", "User", simple_fields, [], config)
        assert "UserRepository" in output

    def test_http_exceptions(self, config, simple_fields):
        output = generate_layer("service", "User", simple_fields, [], config)
        assert "HTTPException" in output
        assert "404" in output

    def test_all_methods_present(self, config, simple_fields):
        output = generate_layer("service", "User", simple_fields, [], config)
        assert "def create(" in output
        assert "def get_by_id(" in output
        assert "def get_all(" in output
        assert "def update(" in output
        assert "def delete(" in output


# ---------------------------------------------------------------------------
# generate_layer — router
# ---------------------------------------------------------------------------

class TestGenerateRouter:
    def test_router_instance(self, config, simple_fields):
        output = generate_layer("router", "User", simple_fields, [], config)
        assert "router = APIRouter(" in output

    def test_prefix(self, config, simple_fields):
        output = generate_layer("router", "User", simple_fields, [], config)
        assert 'prefix="/users"' in output

    def test_all_endpoints(self, config, simple_fields):
        output = generate_layer("router", "User", simple_fields, [], config)
        assert "@router.post(" in output
        assert "@router.get(" in output
        assert "@router.put(" in output
        assert "@router.delete(" in output

    def test_depends_injection(self, config, simple_fields):
        output = generate_layer("router", "User", simple_fields, [], config)
        assert "Depends" in output

    def test_compound_name_prefix(self, config, simple_fields):
        output = generate_layer("router", "BlogPost", simple_fields, [], config)
        assert 'prefix="/blog_posts"' in output


# ---------------------------------------------------------------------------
# generate_all
# ---------------------------------------------------------------------------

class TestGenerateAll:
    def test_full_tier_has_all_layers(self, config, simple_fields):
        result = generate_all("User", simple_fields, [], tier="full", config=config)
        assert set(result.keys()) >= {"model", "repository", "schema", "service", "router"}

    def test_simple_tier_has_subset(self, config, simple_fields):
        result = generate_all("User", simple_fields, [], tier="simple", config=config)
        assert "model" in result
        assert "schema" in result
        assert "router" in result
        assert "repository" not in result
        assert "service" not in result

    def test_all_layers_non_empty(self, config, simple_fields):
        result = generate_all("User", simple_fields, [], tier="full", config=config)
        for layer, content in result.items():
            assert content.strip(), f"Layer '{layer}' returned empty content"


# ---------------------------------------------------------------------------
# resolve_output_path
# ---------------------------------------------------------------------------

class TestResolveOutputPath:
    def test_model_path(self, config, tmp_path):
        path = resolve_output_path("model", "User", config, base_dir=tmp_path)
        assert path == tmp_path / "models" / "user.py"

    def test_repository_path(self, config, tmp_path):
        path = resolve_output_path("repository", "User", config, base_dir=tmp_path)
        assert path == tmp_path / "repositories" / "user_repository.py"

    def test_schema_path(self, config, tmp_path):
        path = resolve_output_path("schema", "User", config, base_dir=tmp_path)
        assert path == tmp_path / "schemas" / "user_schema.py"

    def test_service_path(self, config, tmp_path):
        path = resolve_output_path("service", "User", config, base_dir=tmp_path)
        assert path == tmp_path / "services" / "user_service.py"

    def test_router_path(self, config, tmp_path):
        path = resolve_output_path("router", "User", config, base_dir=tmp_path)
        assert path == tmp_path / "routers" / "user_router.py"

    def test_compound_model_name(self, config, tmp_path):
        path = resolve_output_path("model", "BlogPost", config, base_dir=tmp_path)
        assert path == tmp_path / "models" / "blog_post.py"
