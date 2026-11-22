"""Tests for code generation."""

import ast
from typing import Any

import pytest

from labthings_fastapi.code_generation import (
    NO_ARGUMENTS,
    DataSchemaConverter,
    _class,
    _constant,
    _function,
    _import_from,
    _name,
    assert_legal_name,
    snake_to_camel_case,
    title_to_camel_case,
    title_to_snake_case,
)
from labthings_fastapi.exceptions import IllegalNameError
from labthings_fastapi.thing_description import type_to_dataschema

NAMES_FOR_CONVERSION = (
    ["mixed", "title", "camel", "snake"],
    [
        ("Two words.", "Two Words", "TwoWords", "two_words"),
        ("some, Text{}", "Some Text", "SomeText", "some_text"),
        (
            "MixedUp name_styles",
            "Mixed Up Name Styles",
            "MixedUpNameStyles",
            "mixed_up_name_styles",
        ),
    ],
)


@pytest.mark.parametrize(*NAMES_FOR_CONVERSION)
def test_title_to_snake_case(mixed, title, camel, snake):
    """Test conversion from title case to snake case."""
    assert title_to_snake_case(title) == snake
    assert title_to_snake_case(mixed) == snake


@pytest.mark.parametrize(*NAMES_FOR_CONVERSION)
def test_title_to_camel_case(mixed, title, camel, snake):
    """Test conversion from title case to snake case."""
    assert title_to_camel_case(title) == camel
    assert title_to_camel_case(mixed) == camel


@pytest.mark.parametrize(*NAMES_FOR_CONVERSION)
def test_snake_to_camel_case(mixed, title, camel, snake):
    """Test conversion from title case to snake case.

    Note that `snake_to_camel_case` won't handle
    arbitrary text."""
    assert snake_to_camel_case(snake) == camel


VALID_NAMES = [
    "name",
    "Name",
    "prefix123",
    "snake_case",
    "CamelCase",
    "int",
    "float",
]


@pytest.mark.parametrize("name", VALID_NAMES)
def test_name_valid(name):
    """Check _name works as expected for valid names."""
    ast_name = _name(name, ctx="load")
    assert isinstance(ast_name, ast.Name)
    assert isinstance(ast_name.ctx, ast.Load)
    assert ast_name.id == name
    ast_name = _name(name, ctx="store")
    assert isinstance(ast_name, ast.Name)
    assert isinstance(ast_name.ctx, ast.Store)
    assert ast_name.id == name


INVALID_NAMES = [
    "3name",
    "name.with.dot",
    'name"withquote',
    "45",
    "class",
    "def",
    "(illegal)",
    "#comment",
    "name-with-dashes",
    "exciting!",
    "for",
    "if",
    "",
]


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_name_invalid(name):
    """Check that invalid names raise an error.

    We check `assert_legal_name` but also every function
    that takes a string as an argument and produces an AST
    object.

    This is important to make sure there's no way for strings
    to leak through unsanitised.
    """
    with pytest.raises(IllegalNameError):
        assert_legal_name(name)
    with pytest.raises(IllegalNameError):
        _name(name)
    with pytest.raises(IllegalNameError):
        _class(name, [], [])
    with pytest.raises(IllegalNameError):
        _function(name, NO_ARGUMENTS, [], None)
    with pytest.raises(IllegalNameError):
        _import_from(name, ["legal"])
    with pytest.raises(IllegalNameError):
        _import_from("legal", [name])


@pytest.mark.parametrize(
    ("val", "code"),
    [
        ("string", "'string'"),  # we get quotes
        ("'str'", "\"'str'\""),  # we can nest quotes
        ('"', "'\"'"),  # uses '' to quote "
        ("'", '"\'"'),  # uses "" to quote '
        ("'\"", "'\\'\"'"),  # escapes ' if needed
        ("{foo}", "'{foo}'"),  # {} does nothing
        ("single", "'single'"),  # quotes are ' by default
        ("double", "'double'"),  # quotes are ' by default
        ("\\", r"'\\'"),  # \ gets escaped
        (42, "42"),  # Other datatypes...
        (True, "True"),
        (..., "..."),
        (4.56, "4.56"),
        (None, "None"),
    ],
)
def test_constant(val, code):
    """Check constants are escaped and quoted as needed."""
    assert ast.unparse(_constant(val)) == code


@pytest.mark.parametrize("val", [object(), 1 + 2j])
def test_constant_typeerror(val):
    """Check _constant rejects types it doesn't understand."""
    with pytest.raises(TypeError):
        _constant(val)


def test_import_from():
    """Check _import_from allows dots."""
    stmt = _import_from("foo.bar", ["baz"])
    assert ast.unparse(stmt) == "from foo.bar import baz"


@pytest.mark.parametrize(
    ("type_", "unparsed"),
    [
        (Any, "Any"),
        (str, "str"),
        (int, "int"),
        (float, "float"),
        (bool, "bool"),
        (None, "None"),
        (list, "list[Any]"),  # this is equivalent.
        (list[str], "list[str]"),
        (list[list[list[int]]], "list[list[list[int]]]"),
        (tuple[str, int], "tuple[str, int]"),
        (tuple[int, tuple[float, float]], "tuple[int, tuple[float, float]]"),
        (list[tuple[list[float], int]], "list[tuple[list[float], int]]"),
        (dict, "dict"),
        (int | float, "Union[int, float]"),  # this is equivalent
        # The types below get distorted.
        (tuple[str, ...], "list[str]"),
        (object, "Any"),
    ],
)
def test_dataschemaconverter_roundtrip(type_, unparsed):
    """Test the schema converter can do round-trips.

    This converts Python types to dataschemas, then back to
    a Python type (as an unparsed string).

    This only tests valid cases, but it allows us to do quite a direct
    comparison and keeps the test case definitions succinct.
    """
    schema = type_to_dataschema(type_)
    converter = DataSchemaConverter()
    expression = converter.convert(schema)
    assert ast.unparse(expression) == unparsed


@pytest.mark.parametrize(
    ("type_", "unparsed"),
    [
        (list[list[list[list[list]]]], "list[list[list[Any]]]"),
        (list[tuple[list[tuple[int,]],]], "list[tuple[list[Any],]]"),
    ],
)
def test_dataschema_convert_max_depth(type_, unparsed):
    """Check the converter won't recurse forever."""
    converter = DataSchemaConverter(max_depth=2)
    schema = type_to_dataschema(type_)
    with pytest.warns(match="Recursion depth exceeded"):
        expression = converter.convert(schema)
    assert ast.unparse(expression) == unparsed
