"""Tests for kaira.core.parser."""

from __future__ import annotations

import pytest

from kaira.core.parser import (
    FieldDef,
    RelationDef,
    camel_to_snake,
    parse_fields,
    parse_relation,
    parse_relations_from_json,
    pluralize,
    snake_to_pascal,
    table_name,
    validate_model_name,
)


# ---------------------------------------------------------------------------
# validate_model_name
# ---------------------------------------------------------------------------


class TestValidateModelName:
    def test_valid_pascal_case(self):
        assert validate_model_name("User") == "User"
        assert validate_model_name("BlogPost") == "BlogPost"
        assert validate_model_name("A") == "A"
        assert validate_model_name("UserProfile123") == "UserProfile123"

    def test_lowercase_raises(self):
        with pytest.raises(ValueError, match="PascalCase"):
            validate_model_name("user")

    def test_snake_case_raises(self):
        with pytest.raises(ValueError, match="PascalCase"):
            validate_model_name("user_profile")

    def test_leading_digit_raises(self):
        with pytest.raises(ValueError, match="PascalCase"):
            validate_model_name("1User")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_model_name("")

    def test_with_spaces_raises(self):
        with pytest.raises(ValueError):
            validate_model_name("User Profile")


# ---------------------------------------------------------------------------
# camel_to_snake
# ---------------------------------------------------------------------------


class TestCamelToSnake:
    def test_simple(self):
        assert camel_to_snake("User") == "user"

    def test_compound(self):
        assert camel_to_snake("BlogPost") == "blog_post"

    def test_already_snake(self):
        assert camel_to_snake("user") == "user"

    def test_multiple_words(self):
        assert camel_to_snake("UserProfileAvatar") == "user_profile_avatar"


# ---------------------------------------------------------------------------
# snake_to_pascal
# ---------------------------------------------------------------------------


class TestSnakeToPascal:
    def test_simple(self):
        assert snake_to_pascal("user") == "User"

    def test_compound(self):
        assert snake_to_pascal("blog_post") == "BlogPost"

    def test_already_pascal(self):
        assert snake_to_pascal("User") == "User"


# ---------------------------------------------------------------------------
# pluralize + table_name
# ---------------------------------------------------------------------------


class TestPluralize:
    def test_regular(self):
        assert pluralize("user") == "users"

    def test_y_ending(self):
        assert pluralize("category") == "categories"

    def test_s_ending(self):
        assert pluralize("status") == "statuses"

    def test_ch_ending(self):
        assert pluralize("branch") == "branches"

    def test_table_name_compound(self):
        assert table_name("BlogPost") == "blog_posts"

    def test_table_name_simple(self):
        assert table_name("User") == "users"


# ---------------------------------------------------------------------------
# parse_fields
# ---------------------------------------------------------------------------


class TestParseFields:
    def test_simple_str(self):
        fields = parse_fields("name:str")
        assert len(fields) == 1
        assert fields[0].name == "name"
        assert fields[0].raw_type == "str"
        assert not fields[0].optional

    def test_multiple_fields(self):
        fields = parse_fields("name:str, age:int, score:float, active:bool")
        assert len(fields) == 4
        assert fields[1].name == "age"
        assert fields[1].sqlalchemy_type == "Integer"

    def test_optional_field(self):
        fields = parse_fields("bio:Optional[str]")
        assert fields[0].optional is True
        assert fields[0].python_type == "Optional[str]"
        assert fields[0].sqlalchemy_type == "String"

    def test_datetime_field(self):
        fields = parse_fields("published_at:datetime")
        assert fields[0].sqlalchemy_type == "DateTime"

    def test_empty_string_returns_empty(self):
        assert parse_fields("") == []
        assert parse_fields("   ") == []

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported field type"):
            parse_fields("data:uuid")

    def test_invalid_optional_inner_raises(self):
        with pytest.raises(ValueError, match="Unsupported Optional inner type"):
            parse_fields("data:Optional[uuid]")

    def test_missing_colon_raises(self):
        with pytest.raises(ValueError, match="Invalid field definition"):
            parse_fields("namewithouttype")

    def test_invalid_field_name_raises(self):
        with pytest.raises(ValueError, match="lowercase snake_case"):
            parse_fields("MyField:str")

    def test_whitespace_tolerance(self):
        fields = parse_fields("  name : str , age : int  ")
        assert len(fields) == 2

    def test_sqlalchemy_type_mapping(self):
        fields = parse_fields("a:str, b:int, c:float, d:bool, e:datetime")
        sa_types = [f.sqlalchemy_type for f in fields]
        assert sa_types == ["String", "Integer", "Float", "Boolean", "DateTime"]


# ---------------------------------------------------------------------------
# parse_relation
# ---------------------------------------------------------------------------


class TestParseRelation:
    def test_one_to_many(self):
        r = parse_relation("one-to-many", "Comment")
        assert r.relation_type == "one-to-many"
        assert r.target == "Comment"
        assert r.back_populates == "comments"

    def test_many_to_one(self):
        r = parse_relation("many-to-one", "User")
        assert r.relation_type == "many-to-one"
        assert r.back_populates == "user"

    def test_many_to_many(self):
        r = parse_relation("many-to-many", "Tag")
        assert r.relation_type == "many-to-many"
        assert r.back_populates == "tags"

    def test_with_cascade(self):
        r = parse_relation("one-to-many", "Comment", cascade="all, delete-orphan")
        assert r.cascade == "all, delete-orphan"

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Unknown relation type"):
            parse_relation("has-many", "Comment")

    def test_invalid_target_raises(self):
        with pytest.raises(ValueError, match="PascalCase"):
            parse_relation("one-to-many", "comment")


# ---------------------------------------------------------------------------
# parse_relations_from_json
# ---------------------------------------------------------------------------


class TestParseRelationsFromJson:
    def test_basic(self):
        data = [{"type": "many-to-one", "target": "User"}]
        rels = parse_relations_from_json(data)
        assert len(rels) == 1
        assert rels[0].relation_type == "many-to-one"

    def test_multiple(self):
        data = [
            {"type": "many-to-one", "target": "User"},
            {
                "type": "one-to-many",
                "target": "Comment",
                "cascade": "all, delete-orphan",
            },
        ]
        rels = parse_relations_from_json(data)
        assert len(rels) == 2
        assert rels[1].cascade == "all, delete-orphan"

    def test_empty(self):
        assert parse_relations_from_json([]) == []
