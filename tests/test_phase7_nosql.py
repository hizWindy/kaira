"""Tests for Phase 7 — First-Class NoSQL Architecture & Integration."""

import io
import json
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from kaira.commands.db_cmd import _get_database_url
from kaira.main import app
from kaira.core.drivers import (
    get_engine_driver,
    RelationalEngineDriver,
    DocumentEngineDriver,
)
from kaira.core.stats import build_stats_table, counts_by_name, try_collect_db_stats

runner = CliRunner()


def _render(renderable) -> str:
    """Render a Rich renderable to plain text for assertions."""
    buffer = io.StringIO()
    Console(file=buffer, width=200).print(renderable)
    return buffer.getvalue()


def test_engine_driver_factory():
    """Verify get_engine_driver returns correct driver for DB types."""
    rel_driver = get_engine_driver("postgresql")
    assert isinstance(rel_driver, RelationalEngineDriver)
    assert rel_driver.is_document_db is False
    assert rel_driver.supports_alembic is True
    assert rel_driver.supports_doc_migrations is False

    mongo_driver = get_engine_driver("mongodb")
    assert isinstance(mongo_driver, DocumentEngineDriver)
    assert mongo_driver.is_document_db is True
    assert mongo_driver.supports_alembic is False
    assert mongo_driver.supports_doc_migrations is True


def test_document_driver_relation_snippets():
    """Verify document driver generates correct embedded and linked snippets."""
    driver = DocumentEngineDriver("mongodb")

    # Linked relation
    linked = driver.get_relation_snippet(
        source_model="User",
        target_model="Post",
        relation_type="has-many",
        embedded=False,
    )
    assert "Link" in linked["field_code"]
    assert "posts: list[Link[\"Post\"]]" in linked["field_code"]

    # Embedded relation
    embedded = driver.get_relation_snippet(
        source_model="User",
        target_model="Address",
        relation_type="has-one",
        embedded=True,
    )
    assert "address: \"AddressSchema\"" in embedded["field_code"]


def test_doc_migrate_make_command(tmp_path, monkeypatch):
    """Test generating a NoSQL document migration script."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["migrate-docs", "make", "add_user_roles"])
    assert result.exit_code == 0
    assert "Document migration script created" in result.output

    mig_dir = tmp_path / "migrations_docs"
    assert mig_dir.exists()
    scripts = list(mig_dir.glob("V*__add_user_roles.py"))
    assert len(scripts) == 1
    content = scripts[0].read_text(encoding="utf-8")
    assert "async def upgrade(db)" in content
    assert "async def downgrade(db)" in content


def test_doc_migrate_status_command(tmp_path, monkeypatch):
    """Test running migrate-docs status when scripts exist."""
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["migrate-docs", "make", "init_indexes"])
    result = runner.invoke(app, ["migrate-docs", "status"])
    assert result.exit_code == 0
    assert "Document Migration Scripts" in result.output
    assert "init_indexes" in result.output


def test_seed_generate_mongodb(tmp_path, monkeypatch):
    """Test generating a seed script for a MongoDB project."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text('{"db_type": "mongodb"}', encoding="utf-8")

    result = runner.invoke(app, ["seed", "generate", "User"])
    assert result.exit_code == 0

    seed_file = tmp_path / "seeds" / "seed_user.py"
    assert seed_file.exists()
    content = seed_file.read_text(encoding="utf-8")
    assert "PROJECT_ROOT" in content
    # Called with no argument so every Beanie model is registered (Link support).
    assert "await init_db()" in content
    assert "asyncio.run(seed(count=args.count, force=args.force))" in content


# ── Seed template dispatch & content ─────────────────────────────────────────


def _write_config(tmp_path: Path, db_type: str, fields: list[dict]) -> None:
    """Write a minimal .kaira.json with one generated model."""
    tmp_path.joinpath(".kaira.json").write_text(
        json.dumps(
            {
                "db_type": db_type,
                "models_dir": "models",
                "generated_models": [
                    {"name": "User", "fields": fields, "relations": []}
                ],
            }
        ),
        encoding="utf-8",
    )


def test_mongo_document_allows_undeclared_fields(tmp_path, monkeypatch):
    """The Beanie Document keeps document keys it does not declare.

    A document store holds heterogeneous documents, so a stored key the model
    never declared must stay readable (``model_extra``) and must survive a
    full-document write such as ``replace()``. Without ``extra="allow"`` those
    keys are invisible to application code and dropped by ``replace()``.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text('{"db_type": "mongodb"}', encoding="utf-8")

    result = runner.invoke(
        app, ["generate", "model", "Cooperative", "--fields", "name:str", "--force"]
    )
    assert result.exit_code == 0

    model_code = (tmp_path / "models" / "cooperative.py").read_text(encoding="utf-8")

    assert 'extra="allow"' in model_code
    # pydantic v2 rejects a class that declares both, so the v1-style block must
    # be gone rather than merely supplemented.
    assert "class Config:" not in model_code
    assert "populate_by_name=True" in model_code
    compile(model_code, "cooperative.py", "exec")

    # The request schemas stay strict — dynamic fields are a property of the
    # stored document, not an invitation for clients to inject arbitrary keys.
    schema_code = (tmp_path / "schemas" / "cooperative_schema.py").read_text(
        encoding="utf-8"
    )
    assert 'extra="allow"' not in schema_code


def test_firestore_document_allows_undeclared_fields():
    """The Firestore model keeps undeclared keys, for the same reason as Mongo."""
    template = (
        Path(__file__).parent.parent
        / "kaira"
        / "templates"
        / "firestore"
        / "model_firestore.py.j2"
    ).read_text(encoding="utf-8")

    assert 'extra="allow"' in template
    assert "class Config:" not in template
    # json_schema_extra has to survive the move into ConfigDict.
    assert "json_schema_extra" in template


def test_driver_seed_template_dispatch():
    """Each paradigm resolves its own seed template rather than branching inline."""
    assert get_engine_driver("mongodb").get_seed_template_name() == "seed_model_doc.py.j2"
    assert get_engine_driver("postgresql").get_seed_template_name() == "seed_model_sql.py.j2"
    assert get_engine_driver("sqlite").get_seed_template_name() == "seed_model_sql.py.j2"


def test_seed_generate_sql_uses_sqlalchemy(tmp_path, monkeypatch):
    """A relational project gets the async SQLAlchemy seed, with no sync fallback."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "postgresql", [{"name": "username", "type": "str"}])

    assert runner.invoke(app, ["seed", "generate", "User"]).exit_code == 0
    content = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")

    assert "AsyncSessionLocal" in content
    assert "select(func.count())" in content
    # The sync SessionLocal fallback swallowed real errors; it must stay gone.
    assert "import SessionLocal" not in content
    assert "db.commit()" not in content
    assert "init_db" not in content


def test_seed_typed_values_not_stringified(tmp_path, monkeypatch):
    """datetime/int/bool/float fields seed real typed values, not 'sample_x' strings."""
    monkeypatch.chdir(tmp_path)
    _write_config(
        tmp_path,
        "mongodb",
        [
            {"name": "username", "type": "str"},
            {"name": "age", "type": "int"},
            {"name": "score", "type": "float"},
            {"name": "active", "type": "bool"},
            {"name": "joined_at", "type": "datetime"},
            {"name": "nickname", "type": "Optional[str]"},
        ],
    )

    assert runner.invoke(app, ["seed", "generate", "User"]).exit_code == 0
    content = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")

    assert "'age': i," in content
    assert "'score': float(i)," in content
    assert "'active': i % 2 == 1," in content
    assert "'joined_at': BASE_TIME + timedelta(days=i)," in content
    assert "'username': f'sample_username_{i}'," in content
    # Optional[str] unwraps to str rather than falling through as an unknown type.
    assert "'nickname': f'sample_nickname_{i}'," in content
    # The pre-fix template emitted a string for datetime fields.
    assert "'joined_at': f'sample_joined_at" not in content


def test_seed_record_dict_is_multiline(tmp_path, monkeypatch):
    """Record entries render one per line — trim_blocks once collapsed them."""
    monkeypatch.chdir(tmp_path)
    _write_config(
        tmp_path,
        "mongodb",
        [{"name": "a", "type": "str"}, {"name": "b", "type": "int"}],
    )

    assert runner.invoke(app, ["seed", "generate", "User"]).exit_code == 0
    content = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")

    assert "        'a': f'sample_a_{i}',\n        'b': i,\n    }" in content


def test_seed_bcrypt_import_tracks_password_field(tmp_path, monkeypatch):
    """bcrypt is imported only when a password field is actually seeded."""
    monkeypatch.chdir(tmp_path)

    _write_config(tmp_path, "mongodb", [{"name": "username", "type": "str"}])
    assert runner.invoke(app, ["seed", "generate", "User"]).exit_code == 0
    assert "import bcrypt" not in (tmp_path / "seeds" / "seed_user.py").read_text(
        encoding="utf-8"
    )

    _write_config(tmp_path, "mongodb", [{"name": "password", "type": "str"}])
    assert runner.invoke(app, ["seed", "generate", "User", "--force"]).exit_code == 0
    content = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")
    assert "import bcrypt" in content
    assert "bcrypt.hashpw" in content


def test_seed_scripts_compile(tmp_path, monkeypatch):
    """Generated seed scripts must be syntactically valid for both paradigms."""
    monkeypatch.chdir(tmp_path)
    fields = [
        {"name": "username", "type": "str"},
        {"name": "password", "type": "str"},
        {"name": "joined_at", "type": "datetime"},
    ]

    for db_type in ("mongodb", "postgresql"):
        _write_config(tmp_path, db_type, fields)
        assert runner.invoke(app, ["seed", "generate", "User", "--force"]).exit_code == 0
        source = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")
        compile(source, "seed_user.py", "exec")  # raises SyntaxError on failure


def test_seed_script_is_idempotent_by_default(tmp_path, monkeypatch):
    """The seed guards on existing rows and documents the --force escape hatch."""
    monkeypatch.chdir(tmp_path)

    for db_type, guard in (
        ("mongodb", "existing = await User.count()"),
        ("postgresql", "existing = await session.scalar(select(func.count())"),
    ):
        _write_config(tmp_path, db_type, [{"name": "username", "type": "str"}])
        assert runner.invoke(app, ["seed", "generate", "User", "--force"]).exit_code == 0
        content = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")
        assert guard in content
        assert "if existing and not force:" in content
        assert "--force" in content


# ── init_db contract ─────────────────────────────────────────────────────────


def test_mongo_database_template_init_db_is_callable_without_args():
    """init_db must be callable with no arguments — seeds and migrations rely on it."""
    template = (
        Path(__file__).parent.parent / "kaira" / "templates" / "database_mongodb.py.j2"
    ).read_text(encoding="utf-8")

    assert "async def init_db(document_models: list | None = None)" in template
    assert "def discover_document_models()" in template
    assert "def resolve_db_name(" in template
    # get_default_database() raises when the URI carries no database name, so the
    # client must be indexed by an explicitly resolved name instead.
    assert "_client.get_default_database()" not in template
    assert "_client[resolve_db_name()]" in template


# ── Provisioning ─────────────────────────────────────────────────────────────


def test_db_init_requires_generated_project(tmp_path, monkeypatch):
    """kaira db init fails clearly when there is no project to provision."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kaira.json").write_text('{"db_type": "mongodb"}', encoding="utf-8")

    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 1
    assert "No generated project found" in result.output


# ── Stats collection ─────────────────────────────────────────────────────────


def test_counts_by_name_and_delta_table():
    """Stats rows reduce to a count map and render a signed change column."""
    rows = [{"name": "users", "count": 5}, {"name": "posts", "count": 0}]
    assert counts_by_name(rows) == {"users": 5, "posts": 0}

    table = build_stats_table("mongodb", "shop", rows, before={"users": 2, "posts": 0})
    rendered = _render(table)
    assert "Collection" in rendered and "Documents" in rendered
    assert "+3" in rendered  # users grew from 2 to 5


def test_stats_table_columns_differ_by_paradigm():
    """Relational stats show a Columns count; document stats do not."""
    rows = [{"name": "users", "count": 1, "columns": 4}]

    assert "Columns" in _render(build_stats_table("postgresql", "app", rows))
    assert "Columns" not in _render(build_stats_table("mongodb", "app", rows))


def test_try_collect_db_stats_swallows_connection_errors():
    """Stats are a convenience: an unreachable database must not raise."""
    assert try_collect_db_stats("postgresql", "postgresql+asyncpg://x:y@127.0.0.1:1/none") is None


# ── DATABASE_URL resolution ──────────────────────────────────────────────────


def test_database_url_falls_back_to_app_env_profile(tmp_path, monkeypatch):
    """kaira init writes the URL to .env.<APP_ENV>; resolution must read it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")

    # Mirrors a generated Mongo project: .env has the line commented out.
    (tmp_path / ".env").write_text(
        "# DATABASE_URL=mongodb://localhost:27017/app\n", encoding="utf-8"
    )
    (tmp_path / ".env.development").write_text(
        "DATABASE_URL=mongodb://localhost:27017/app\n", encoding="utf-8"
    )

    assert _get_database_url() == "mongodb://localhost:27017/app"


def test_database_url_prefers_active_env_over_profile(tmp_path, monkeypatch):
    """An uncommented .env value wins over the profile file, matching Settings."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")

    (tmp_path / ".env").write_text("DATABASE_URL=mongodb://active/db\n", encoding="utf-8")
    (tmp_path / ".env.development").write_text(
        "DATABASE_URL=mongodb://profile/db\n", encoding="utf-8"
    )

    assert _get_database_url() == "mongodb://active/db"


def test_database_url_ignores_commented_lines(tmp_path, monkeypatch):
    """A fully commented-out configuration resolves to nothing, not the comment."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "#DATABASE_URL=mongodb://nope/db\n  # DATABASE_URL=mongodb://also-nope/db\n",
        encoding="utf-8",
    )

    assert _get_database_url() == ""


def test_seed_generate_uses_live_model_ast_fields(tmp_path, monkeypatch):
    """seed generate parses live model files via AST so updated model fields reflect in seeds."""
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path, "mongodb", [{"name": "old_field", "type": "str"}])

    models_dir = tmp_path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    model_file = models_dir / "user.py"
    model_file.write_text(
        "from beanie import Document\n"
        "from pydantic import Field\n\n"
        "class User(Document):\n"
        "    uuid: str = Field(...)\n"
        "    user_name: str = Field(...)\n"
        "    password: str = Field(...)\n"
        "    email: str = Field(...)\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["seed", "generate", "User", "--force"])
    assert result.exit_code == 0

    seed_file = tmp_path / "seeds" / "seed_user.py"
    assert seed_file.exists()
    content = seed_file.read_text(encoding="utf-8")

    assert "'user_name': f'sample_user_name_{i}'," in content
    assert "'password': bcrypt.hashpw" in content
    assert "'email': f'user{i}@example.com'," in content
    assert "'old_field'" not in content

