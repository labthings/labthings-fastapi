"""Tests for code generation."""

import ast
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from labthings_fastapi.code_generation import (
    NO_ARGUMENTS,
    RUFF_BINARY,
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
    write_client_module,
)
from labthings_fastapi.exceptions import IllegalNameError
from labthings_fastapi.testing import create_thing_without_server
from labthings_fastapi.thing_description import type_to_dataschema
from labthings_fastapi.thing_description._model import DataSchema

from .example_things.thing_with_simple_types import SimpleTypeThing

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
        ("ALLCAPS", "Allcaps", "Allcaps", "allcaps"),
        ("Word.", "Word", "Word", "word"),
        ("CamelCASE", "Camel CASE", "CamelCase", "camel_case"),
        ("snake_case", "Snake Case", "SnakeCase", "snake_case"),
        ("lower", "Lower", "Lower", "lower"),
        ("snakeCASE_word", "Snake Case Word", "SnakeCaseWord", "snake_case_word"),
    ],
)


@pytest.mark.parametrize(*NAMES_FOR_CONVERSION)
def test_title_to_snake_case(mixed, title, camel, snake):
    """Test conversion from title case to snake case."""
    assert title_to_snake_case(title) == snake
    assert title_to_snake_case(camel) == snake
    assert title_to_snake_case(mixed) == snake


@pytest.mark.parametrize(*NAMES_FOR_CONVERSION)
def test_title_to_camel_case(mixed, title, camel, snake):
    """Test conversion from title case to snake case."""
    assert title_to_camel_case(title) == camel
    assert title_to_camel_case(mixed) == camel
    assert title_to_camel_case(snake) == camel


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
def test_dataschemaconverter_convert_roundtrip(type_, unparsed):
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
    ("schema", "unparsed"),
    [
        (DataSchema(type="object"), "dict"),
        (DataSchema(type="array"), "list"),
    ],
)
def test_dataschemaconverter_convert_direct(schema, unparsed):
    """Test the schema converter against some statically defined schemas.

    This allows us to test for some cases that aren't generated by
    `type_to_dataschema`.
    """
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
def test_dataschemaconverter_convert_max_depth(type_, unparsed):
    """Check the converter won't recurse forever."""
    converter = DataSchemaConverter(max_depth=2)
    schema = type_to_dataschema(type_)
    with pytest.warns(match="Recursion depth exceeded"):
        expression = converter.convert(schema)
    assert ast.unparse(expression) == unparsed


def test_dataschemaconverter_convert_fallback():
    """Test a DataSchema that doesn't match.

    If none of the `_convert_{datatype}` functions match (including
    `_convert_any` which matches no type information), we fall back
    to `Any`. That requires a type that isn't handled. We use a
    deliberately invalid type to check that case.
    """
    converter = DataSchemaConverter()
    with pytest.warns(match="falling back to `Any`"):
        converter.convert(DataSchema.model_construct(type="unsupported"))


def test_dataschemaconverter_input_model_to_arguments_errors():
    """Test the error condition if an invalid DataSchema is passed in.

    This is tested with valid data elsewhere - it's easier to evaluate
    in the context of a function definition, because we can `unparse` that.
    """
    converter = DataSchemaConverter()
    with pytest.raises(TypeError, match="Only object models are supported"):
        # We should only ever call the function with a DataSchema having a
        # type of None or `object`. Non-keyword arguments are not supported
        # by the WoT data model.
        converter.input_model_to_arguments(DataSchema(type="integer"))
    # Here, the input has the correct type, but there is no "properties"
    # mapping, so we return NO_ARGUMENTS
    args = converter.input_model_to_arguments(DataSchema(type="object"))
    assert args is NO_ARGUMENTS


def test_generated_client():
    """Test the generated client code matches our expectation.

    This compares a generated client module to a previously-generated file.
    It's mostly intended to make it obvious when something changes.
    It's important to check that the file saved in the repository is correct
    by manual inspection, and not simply to regenerate it to make the test pass.

    Note that we only check the output run through ruff. Different Python
    versions have slightly different behaviours in `ast.unparse` but these
    get normalised out by `ruff`.
    """
    assert RUFF_BINARY is not None
    thing = create_thing_without_server(SimpleTypeThing)
    td = thing.thing_description()
    cmp_fname = "thing_with_simple_types_client.py"
    here = Path(__file__).parent
    examples = here / "example_things"
    with TemporaryDirectory() as tempdir:
        output = Path(tempdir) / "client.py"
        write_client_module(td, output, use_ruff=True)
        with open(output) as f:
            written = f.readlines()
        print("".join(written))
        with open(examples / cmp_fname) as f:
            expected = f.readlines()
        assert written == expected
