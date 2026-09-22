"""Tests for embedded (nested) document field types.

An embedded type is a value object stored inside another model — a sub-document
on MongoDB/Firestore, a JSON column on SQL. The regression these guard against
is ``kaira sync`` silently deleting an embedded field because the introspector
only recognised scalars.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kaira.commands.seed_cmd import _parse_live_model_fields, render_seed
from kaira.config import (
    KairaConfig,
    embedded_model_names,
    get_config,
    register_embedded_model,
)
from kaira.core.parser import FieldDef, parse_fields
from kaira.main import app

runner = CliRunner()

EMBEDDED = {"EmergencyContact"}


def _init_project(tmp_path: Path, db_type: str) -> None:
    """Write a minimal .kaira.json with one registered embedded type."""
    tmp_path.joinpath(".kaira.json").write_text(
        json.dumps(
            {
                "db_type": db_type,
                "models_dir": "models",
                "generated_models": [],
                "embedded_models": [
                    {
                        "name": "EmergencyContact",
                        "fields": [
                            {"name": "name", "type": "str"},
                            {"name": "phone", "type": "str"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


# ── Parsing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "declared, python_type, optional, is_list",
    [
        ("EmergencyContact", "EmergencyContact", False, False),
        ("Optional[EmergencyContact]", "Optional[EmergencyContact]", True, False),
        ("list[EmergencyContact]", "list[EmergencyContact]", False, True),
        ("List[EmergencyContact]", "list[EmergencyContact]", False, True),
    ],
)
def test_embedded_type_forms(declared, python_type, optional, is_list):
    """Plain, Optional and list forms all resolve to an embedded field."""
    (field,) = parse_fields(f"contact:{declared}", embedded=EMBEDDED)
    assert field.is_embedded
    assert field.embedded_model == "EmergencyContact"
    assert field.python_type == python_type
    assert field.optional is optional
    assert field.is_list is is_list


def test_embedded_field_maps_to_json_on_sql():
    """SQL has no sub-document type, so an embedded field becomes JSON."""
    (field,) = parse_fields("contact:EmergencyContact", embedded=EMBEDDED)
    assert field.sqlalchemy_type == "JSON"


def test_unregistered_pascal_type_is_rejected():
    """An unknown PascalCase type is a typo far more often than an intent."""
    with pytest.raises(ValueError) as exc:
        parse_fields("contact:NotDeclared", embedded=EMBEDDED)
    message = str(exc.value)
    assert "NotDeclared" in message
    # The error has to say how to fix it, not just what failed.
    assert "kaira generate embedded" in message


def test_scalar_parsing_is_unchanged_without_embedded_types():
    """Projects with no embedded types keep the original scalar-only behaviour."""
    fields = parse_fields("name:str, age:int, bio:Optional[str]", embedded=set())
    assert [f.python_type for f in fields] == ["str", "int", "Optional[str]"]
    assert not any(f.is_embedded for f in fields)

    with pytest.raises(ValueError):
        parse_fields("contact:EmergencyContact", embedded=set())


def test_scalar_fields_report_not_embedded():
    """is_embedded must stay False for every scalar type."""
    assert not FieldDef(name="x", raw_type="str").is_embedded
    assert not FieldDef(name="x", raw_type="Optional[datetime]").is_embedded


# ── Config registry ──────────────────────────────────────────────────────────


def test_register_embedded_model_upserts():
    """Re-registering a name replaces its fields rather than duplicating it."""
    config = KairaConfig()
    register_embedded_model(config, "EmergencyContact", [{"name": "a", "type": "str"}])
    register_embedded_model(config, "EmergencyContact", [{"name": "b", "type": "str"}])

    assert len(config.embedded_models) == 1
    assert config.embedded_models[0]["fields"] == [{"name": "b", "type": "str"}]
    assert embedded_model_names(config) == {"EmergencyContact"}


# ── Generation ───────────────────────────────────────────────────────────────


def test_generate_embedded_creates_plain_pydantic_model(tmp_path, monkeypatch):
    """An embedded type gets one BaseModel — no repository, service or router."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    result = runner.invoke(
        app,
        [
            "generate",
            "embedded",
            "Address",
            "--fields",
            "street:str, city:str",
            "--force",
        ],
    )
    assert result.exit_code == 0

    model = tmp_path / "models" / "address.py"
    assert model.exists()
    code = model.read_text(encoding="utf-8")
    assert "class Address(BaseModel)" in code
    assert "Document" not in code
    compile(code, "address.py", "exec")

    for layer in ("repositories", "services", "routers"):
        assert not (tmp_path / layer / f"address_{layer[:-3]}.py").exists()

    # It must be registered, otherwise no model could reference it.
    config = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))
    assert any(e["name"] == "Address" for e in config["embedded_models"])


def test_embedded_field_generates_nested_annotation_on_mongo(tmp_path, monkeypatch):
    """The Beanie Document declares the nested type and imports it."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    result = runner.invoke(
        app,
        [
            "generate",
            "model",
            "Credential",
            "--fields",
            "sss_id:str, emergency_contact:EmergencyContact",
            "--force",
        ],
    )
    assert result.exit_code == 0

    model_code = (tmp_path / "models" / "credential.py").read_text(encoding="utf-8")
    assert "from models.emergency_contact import EmergencyContact" in model_code
    assert "emergency_contact: EmergencyContact" in model_code
    compile(model_code, "credential.py", "exec")

    schema_code = (tmp_path / "schemas" / "credential_schema.py").read_text(
        encoding="utf-8"
    )
    assert "from models.emergency_contact import EmergencyContact" in schema_code
    assert "emergency_contact: EmergencyContact" in schema_code
    # Update is PATCH-style, so the nested field must be optional there.
    assert (
        "emergency_contact: Optional[EmergencyContact] = None" in schema_code
        or "emergency_contact: EmergencyContact | None = None" in schema_code
    )
    compile(schema_code, "credential_schema.py", "exec")


def test_embedded_field_becomes_json_column_on_sql(tmp_path, monkeypatch):
    """SQL stores the nested object in a JSON column, with JSON imported."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "sqlite")

    result = runner.invoke(
        app,
        [
            "generate",
            "model",
            "Credential",
            "--fields",
            "sss_id:str, emergency_contact:EmergencyContact",
            "--force",
        ],
    )
    assert result.exit_code == 0

    model_code = (tmp_path / "models" / "credential.py").read_text(encoding="utf-8")
    assert "JSON," in model_code
    assert "mapped_column(JSON, nullable=False)" in model_code
    compile(model_code, "credential.py", "exec")


def test_embedded_list_defaults_to_empty_not_none(tmp_path, monkeypatch):
    """A list of embedded docs defaults to [] so callers can append safely."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    result = runner.invoke(
        app,
        [
            "generate",
            "model",
            "Patient",
            "--fields",
            "contacts:list[EmergencyContact]",
            "--force",
        ],
    )
    assert result.exit_code == 0

    model_code = (tmp_path / "models" / "patient.py").read_text(encoding="utf-8")
    assert (
        "contacts: list[EmergencyContact] = Field(default_factory=list)" in model_code
    )


# ── Sync (the reported bug) ──────────────────────────────────────────────────


def test_sync_preserves_embedded_field(tmp_path, monkeypatch):
    """Regression: sync used to silently delete an embedded field.

    The introspector only accepted scalars, so an embedded annotation was
    dropped and the regenerated model lost the field with no warning.
    """
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "Credential",
                "--fields",
                "sss_id:str, emergency_contact:EmergencyContact",
                "--force",
            ],
        ).exit_code
        == 0
    )

    model_path = tmp_path / "models" / "credential.py"
    assert "emergency_contact: EmergencyContact" in model_path.read_text(
        encoding="utf-8"
    )

    # A sync that genuinely regenerates the model layer.
    result = runner.invoke(
        app, ["sync", "model", "Credential", "--fields", "pagibig_id:str", "--force"]
    )
    assert result.exit_code == 0

    after = model_path.read_text(encoding="utf-8")
    assert "emergency_contact: EmergencyContact" in after, (
        "embedded field was destroyed"
    )
    assert "pagibig_id" in after, "new scalar field was not added"

    schema_after = (tmp_path / "schemas" / "credential_schema.py").read_text(
        encoding="utf-8"
    )
    assert "emergency_contact: EmergencyContact" in schema_after


def test_seed_includes_embedded_field_as_nested_dict(tmp_path, monkeypatch):
    """Regression: seeds omitted embedded fields, so seeding crashed.

    A required embedded field left out of the record dict fails validation the
    moment the seed runs, so the sample value has to be a nested dict built
    from the embedded type's own fields.
    """
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "Credential",
                "--fields",
                "sss_id:str, emergency_contact:EmergencyContact",
                "--force",
            ],
        ).exit_code
        == 0
    )

    result = runner.invoke(app, ["seed", "generate", "Credential", "--force"])
    assert result.exit_code == 0

    seed_code = (tmp_path / "seeds" / "seed_credential.py").read_text(encoding="utf-8")
    assert "'emergency_contact':" in seed_code, "embedded field missing from seed"
    # A nested dict of the embedded type's own fields, not a flat string.
    assert "'emergency_contact': {'name':" in seed_code
    assert "'phone':" in seed_code
    assert "sample_emergency_contact" not in seed_code
    compile(seed_code, "seed_credential.py", "exec")


def test_seed_embedded_list_is_a_list_of_dicts(tmp_path, monkeypatch):
    """A list of embedded docs seeds as [ {...} ], not a bare dict or string."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "Patient",
                "--fields",
                "contacts:list[EmergencyContact]",
                "--force",
            ],
        ).exit_code
        == 0
    )

    assert runner.invoke(app, ["seed", "generate", "Patient", "--force"]).exit_code == 0

    seed_code = (tmp_path / "seeds" / "seed_patient.py").read_text(encoding="utf-8")
    assert "'contacts': [{'name':" in seed_code
    compile(seed_code, "seed_patient.py", "exec")


def test_seed_picks_up_hand_added_embedded_field(tmp_path, monkeypatch):
    """A hand-written embedded field is seeded even before it reaches the snapshot.

    Seeds prefer live inspection of the model file so hand edits are honoured.
    The snapshot cannot help here — it has never seen this field — so the AST
    pass is what has to recognise it.
    """
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    assert (
        runner.invoke(
            app,
            ["generate", "model", "Credential", "--fields", "sss_id:str", "--force"],
        ).exit_code
        == 0
    )

    # Hand-edit the model, exactly as a developer would.
    model_path = tmp_path / "models" / "credential.py"
    code = model_path.read_text(encoding="utf-8")
    code = code.replace(
        "    sss_id: str = Field(..., max_length=255)",
        "    sss_id: str = Field(..., max_length=255)\n"
        "    emergency_contact: EmergencyContact",
    )
    model_path.write_text(code, encoding="utf-8")

    snapshot = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))
    credential = next(
        m for m in snapshot["generated_models"] if m["name"] == "Credential"
    )
    assert all(f["name"] != "emergency_contact" for f in credential["fields"])

    assert (
        runner.invoke(app, ["seed", "generate", "Credential", "--force"]).exit_code == 0
    )

    seed_code = (tmp_path / "seeds" / "seed_credential.py").read_text(encoding="utf-8")
    assert "'emergency_contact': {'name':" in seed_code


def test_seed_on_sql_recovers_embedded_from_snapshot(tmp_path, monkeypatch):
    """SQL declares `Mapped[dict]`, so only the snapshot knows the real type.

    Introspecting the model file cannot recover the embedded type on SQL, and
    the snapshot must not be overwritten with the field list that lost it.
    """
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "sqlite")

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "Credential",
                "--fields",
                "sss_id:str, emergency_contact:EmergencyContact",
                "--force",
            ],
        ).exit_code
        == 0
    )

    assert (
        runner.invoke(app, ["seed", "generate", "Credential", "--force"]).exit_code == 0
    )

    seed_code = (tmp_path / "seeds" / "seed_credential.py").read_text(encoding="utf-8")
    assert "'emergency_contact': {'name':" in seed_code
    compile(seed_code, "seed_credential.py", "exec")

    # The snapshot must still carry the embedded type, not a degraded copy.
    config = json.loads((tmp_path / ".kaira.json").read_text(encoding="utf-8"))
    credential = next(
        m for m in config["generated_models"] if m["name"] == "Credential"
    )
    types = {f["name"]: f["type"] for f in credential["fields"]}
    assert types["emergency_contact"] == "EmergencyContact"


def _init_auth_project(tmp_path: Path, db_type: str = "sqlite") -> None:
    """Write a .kaira.json for a JWT project (no embedded types needed)."""
    tmp_path.joinpath(".kaira.json").write_text(
        json.dumps(
            {
                "db_type": db_type,
                "models_dir": "models",
                "auth_type": "jwt",
                "api_version": "v1",
                "generated_models": [],
                "embedded_models": [],
            }
        ),
        encoding="utf-8",
    )


def test_seeded_password_plaintext_is_recoverable(tmp_path, monkeypatch):
    """A seeded password is hashed, so the seed must surface the plaintext.

    The hash and the printed credentials both read ``plain_password``, so a
    change to the sample scheme cannot leave the printout lying.
    """
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "User",
                "--fields",
                "username:str, password:str",
                "--force",
            ],
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["seed", "generate", "User", "--force"]).exit_code == 0

    seed_code = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")
    assert "def plain_password(i: int) -> str:" in seed_code
    # Single source of truth: the hash is built from the same helper that the
    # credentials printout reads.
    assert "bcrypt.hashpw(plain_password(i).encode()" in seed_code
    assert "Test credentials" in seed_code
    assert "{plain_password(i)}" in seed_code
    compile(seed_code, "seed_user.py", "exec")


def test_seed_prints_login_command_for_auth_model(tmp_path, monkeypatch):
    """The User model gets a ready-to-run login command at the mounted path."""
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "User",
                "--fields",
                "username:str, password:str",
                "--force",
            ],
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["seed", "generate", "User", "--force"]).exit_code == 0

    seed_code = (tmp_path / "seeds" / "seed_user.py").read_text(encoding="utf-8")
    # Must match where the auth router is actually mounted.
    assert "/api/v1/auth/login" in seed_code
    assert "import json" in seed_code


def test_seed_omits_credentials_when_no_password(tmp_path, monkeypatch):
    """Models without a password get no credentials noise."""
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(
            app, ["generate", "model", "Article", "--fields", "title:str", "--force"]
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["seed", "generate", "Article", "--force"]).exit_code == 0

    seed_code = (tmp_path / "seeds" / "seed_article.py").read_text(encoding="utf-8")
    assert "plain_password" not in seed_code
    assert "Test credentials" not in seed_code
    assert "import bcrypt" not in seed_code
    compile(seed_code, "seed_article.py", "exec")


def test_seed_skips_login_hint_for_non_auth_model(tmp_path, monkeypatch):
    """A non-User model with a password shows credentials but no login curl.

    The generated auth service queries ``User`` specifically, so a login
    command aimed at any other model would simply not work.
    """
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "Admin",
                "--fields",
                "username:str, password:str",
                "--force",
            ],
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["seed", "generate", "Admin", "--force"]).exit_code == 0

    seed_code = (tmp_path / "seeds" / "seed_admin.py").read_text(encoding="utf-8")
    assert "plain_password" in seed_code
    assert "Test credentials" in seed_code
    assert "/auth/login" not in seed_code
    compile(seed_code, "seed_admin.py", "exec")


def test_seed_run_autosync_preserves_credentials_block(tmp_path, monkeypatch):
    """Regression: `seed run` auto-sync stripped the credentials helper.

    It assembled its own template context instead of reusing render_seed, so
    keys it did not know about vanished — leaving build_record calling a
    plain_password() that no longer existed.
    """
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "User",
                "--fields",
                "username:str, password:str",
                "--force",
            ],
        ).exit_code
        == 0
    )
    assert runner.invoke(app, ["seed", "generate", "User", "--force"]).exit_code == 0

    # Add a field to the model so auto-sync has something to reconcile.
    model_path = tmp_path / "models" / "user.py"
    code = model_path.read_text(encoding="utf-8")
    code = code.replace(
        "    username: Mapped[str] = mapped_column(String, nullable=False)",
        "    username: Mapped[str] = mapped_column(String, nullable=False)\n"
        "    nickname: Mapped[str] = mapped_column(String, nullable=False)",
    )
    model_path.write_text(code, encoding="utf-8")

    live = _parse_live_model_fields(model_path, "User")
    assert any(f["name"] == "nickname" for f in live), "model edit not detected"

    # Re-render the way auto-sync now does, through the shared builder.
    config = get_config()
    content, _ = render_seed("User", config, tmp_path, fields_override=live)

    assert "'nickname'" in content, "new field not picked up"
    assert "def plain_password" in content, "credentials helper was stripped"
    assert "Test credentials" in content
    # The password hash must never reference a helper that is not emitted.
    assert ("plain_password(i)" in content) == ("def plain_password" in content)
    compile(content, "seed_user.py", "exec")


def test_sql_auth_service_is_async(tmp_path, monkeypatch):
    """Regression: the SQL auth service ran sync queries on an AsyncSession.

    `db.execute(...)` without `await` returns a coroutine; `.scalar_one_or_none()`
    then raises, and a bare `except` turned every login into a 401.
    """
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(app, ["auth", "generate", "--type", "jwt", "--force"]).exit_code
        == 0
    )

    service = (tmp_path / "auth" / "service.py").read_text(encoding="utf-8")
    assert "async def authenticate_user" in service
    assert "await db.execute(" in service
    # The un-awaited form must be gone entirely.
    assert "= db.execute(" not in service
    assert "from sqlalchemy.orm import Session" not in service
    compile(service, "service.py", "exec")

    router = (tmp_path / "auth" / "router.py").read_text(encoding="utf-8")
    assert "await AuthService.authenticate_user(" in router
    assert "await AuthService.blacklist_token(" in router
    compile(router, "router.py", "exec")


def test_oauth2_token_url_matches_mounted_path(tmp_path, monkeypatch):
    """Swagger's Authorize button must post to the versioned auth path."""
    monkeypatch.chdir(tmp_path)
    _init_auth_project(tmp_path)

    assert (
        runner.invoke(app, ["auth", "generate", "--type", "jwt", "--force"]).exit_code
        == 0
    )

    deps = (tmp_path / "auth" / "dependencies.py").read_text(encoding="utf-8")
    assert 'tokenUrl="/api/v1/auth/login"' in deps
    compile(deps, "dependencies.py", "exec")


def test_sync_preserves_embedded_list_field(tmp_path, monkeypatch):
    """`list[Embedded]` must not be mistaken for a relationship and dropped."""
    monkeypatch.chdir(tmp_path)
    _init_project(tmp_path, "mongodb")

    assert (
        runner.invoke(
            app,
            [
                "generate",
                "model",
                "Patient",
                "--fields",
                "contacts:list[EmergencyContact]",
                "--force",
            ],
        ).exit_code
        == 0
    )

    result = runner.invoke(
        app, ["sync", "model", "Patient", "--fields", "full_name:str", "--force"]
    )
    assert result.exit_code == 0

    after = (tmp_path / "models" / "patient.py").read_text(encoding="utf-8")
    assert "contacts: list[EmergencyContact]" in after
    assert "full_name" in after
