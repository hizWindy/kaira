"""Tests for Khaira Framework Library Abstraction Layer."""

from __future__ import annotations

import ast

from khaira.models import Mapped


def test_khaira_top_level_exports() -> None:
    """Verify top-level primitives can be imported from khaira."""
    import khaira
    from khaira import (
        APIRouter,
        Depends,
        Document,
        HTTPException,
        KairaApp,
        KhairaApp,
        Model,
        Router,
        Schema,
        status,
    )

    assert Router is APIRouter
    assert issubclass(Schema, object)
    assert hasattr(HTTPException, "status_code") or callable(HTTPException)
    assert status.HTTP_200_OK == 200
    assert KhairaApp is KairaApp
    assert Model is not None
    assert Document is not None
    assert callable(Depends)
    assert khaira.__version__ is not None


def test_kaira_top_level_exports() -> None:
    """Verify top-level primitives can be imported from kaira."""
    import kaira
    from kaira import (
        APIRouter,
        Depends,
        Document,
        HTTPException,
        KairaApp,
        KhairaApp,
        Model,
        Router,
        Schema,
        status,
    )

    assert Router is APIRouter
    assert issubclass(Schema, object)
    assert status.HTTP_201_CREATED == 201
    assert callable(Depends)
    assert Model is not None
    assert Document is not None
    assert KhairaApp is KairaApp
    assert hasattr(kaira, "get_config")
    assert HTTPException is not None


def test_khaira_http_abstraction() -> None:
    """Test from khaira.http import Router, Depends, HTTPException, status, Query, Request, Response."""
    from khaira.http import (
        APIRouter,
        BackgroundTasks,
        Body,
        Depends,
        HTTPException,
        Path,
        Query,
        Request,
        Response,
        Router,
        Security,
        status,
    )

    router = Router(prefix="/items", tags=["items"])
    assert router.prefix == "/items"
    assert Router is APIRouter

    exc = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    assert exc.status_code == 404
    assert exc.detail == "Item not found"

    # Verify helper primitives exist
    assert callable(Depends)
    assert callable(Security)
    assert callable(Query)
    assert callable(Path)
    assert callable(Body)
    assert BackgroundTasks is not None
    assert Request is not None
    assert Response is not None


def test_kaira_http_abstraction() -> None:
    """Test from kaira.http import Router, Depends, HTTPException, status."""
    from kaira.http import Depends, HTTPException, Router, status

    router = Router()
    assert router is not None
    assert callable(Depends)
    assert HTTPException is not None
    assert status.HTTP_200_OK == 200


def test_khaira_auth_abstraction() -> None:
    """Test from khaira.auth import OAuth2PasswordBearer, JWT, hash_password, etc."""
    from khaira.auth import (
        JWT,
        ApiKey,
        HTTPBearer,
        JWTManager,
        OAuth2,
        OAuth2PasswordBearer,
        OAuth2PasswordRequestForm,
        SecurityScopes,
        hash_password,
        verify_password,
    )

    scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
    assert scheme.model.flows.password.tokenUrl == "/api/v1/auth/login"

    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)

    assert ApiKey is not None
    assert HTTPBearer is not None
    assert JWT is not None
    assert JWTManager is not None
    assert OAuth2 is not None
    assert OAuth2PasswordRequestForm is not None
    assert SecurityScopes is not None


def test_khaira_schemas_abstraction() -> None:
    """Test from khaira.schemas import Schema, Field, ConfigDict."""
    from khaira.schemas import ConfigDict, Field, Schema

    class UserSchema(Schema):
        id: int
        username: str = Field(..., min_length=3)
        email: str

        model_config = ConfigDict(str_strip_whitespace=True)

    user = UserSchema(id=1, username="  alice  ", email="alice@example.com")
    assert user.username == "alice"
    assert user.id == 1
    assert user.model_dump() == {
        "id": 1,
        "username": "alice",
        "email": "alice@example.com",
    }


def test_khaira_models_abstraction() -> None:
    """Test from khaira.models import Model, Column, Integer, String, relationship, select."""
    from khaira.models import (
        Boolean,
        Column,
        DateTime,
        ForeignKey,
        Integer,
        Model,
        String,
        Table,
        mapped_column,
        relationship,
        select,
    )

    class Item(Model):
        __tablename__ = "items_test"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        title: Mapped[str] = mapped_column(String(50))

    stmt = select(Item).where(Item.title == "widget")
    assert "items_test" in str(stmt)
    assert Column is not None
    assert Boolean is not None
    assert DateTime is not None
    assert ForeignKey is not None
    assert Table is not None
    assert relationship is not None


def test_khaira_database_abstraction() -> None:
    """Test from khaira.database import Database, AsyncSession, Session, get_db."""
    from khaira.database import AsyncSession, Database, Session, get_db

    db = Database("sqlite+aiosqlite:///./test.db")
    assert db.get_dsn() == "sqlite+aiosqlite:///./test.db"
    assert AsyncSession is not None
    assert Session is not None
    assert callable(get_db)


def test_khaira_rate_limit_abstraction() -> None:
    """Test from khaira.rate_limit import Limiter, RateLimitMiddleware."""
    from khaira.rate_limit import InMemoryLimiter, Limiter, RateLimitMiddleware

    limiter = InMemoryLimiter(limit=2, window_seconds=60)
    assert limiter.is_allowed("client-1") is True
    assert limiter.is_allowed("client-1") is True
    assert limiter.is_allowed("client-1") is False
    assert Limiter is not None
    assert RateLimitMiddleware is not None


def test_khaira_security_abstraction() -> None:
    """Test from khaira.security import Encryption, Fernet."""
    from khaira.security import Encryption, Fernet

    enc = Encryption()
    token = enc.encrypt(b"my-secret-key")
    decrypted = enc.decrypt(token)
    assert decrypted == b"my-secret-key"
    assert Fernet is not None


def test_khaira_other_submodules() -> None:
    """Test cache, task, ai, logging, tracing submodules."""
    from khaira.ai import RAG, Agent
    from khaira.cache import Cache
    from khaira.logging import logger
    from khaira.task import Task
    from khaira.tracing import Tracer

    assert Cache is not None
    assert Task is not None
    assert Agent is not None
    assert RAG is not None
    assert logger is not None
    assert Tracer is not None


def test_rendered_templates_use_khaira_abstractions() -> None:
    """Ensure generated templates use khaira abstractions and parse into valid AST."""
    from kaira.core.generator import render_template

    context = {
        "model_name": "Product",
        "snake_name": "product",
        "table_name": "products",
        "fields": [],
        "models_dir": "models",
        "schemas_dir": "schemas",
        "services_dir": "services",
        "repositories_dir": "repositories",
        "db_type": "sqlite",
        "has_auth_guard": False,
        "api_version": "v1",
        "has_embedded": False,
        "needs_optional": False,
        "embedded_imports": [],
        "one_to_many": [],
        "many_to_one": [],
        "many_to_many": [],
        "server_managed_fields": ["id", "uuid", "created_at", "updated_at"],
    }

    # Test router template
    router_code = render_template("router.py.j2", context)
    assert "from khaira.http import Router, Depends" in router_code
    ast.parse(router_code)

    # Test service template
    service_code = render_template("service.py.j2", context)
    assert "from khaira.http import HTTPException, status" in service_code
    ast.parse(service_code)

    # Test schema template
    schema_code = render_template("schema.py.j2", context)
    assert "from khaira.schemas import Schema" in schema_code
    ast.parse(schema_code)

    # Test auth dependencies template
    auth_dep_code = render_template("auth_jwt_dependencies.py.j2", context)
    assert "from khaira.http import Depends, HTTPException, status" in auth_dep_code
    assert "from khaira.auth import OAuth2PasswordBearer" in auth_dep_code
    ast.parse(auth_dep_code)
