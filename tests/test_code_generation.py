"""Tests for code generation."""

import ast
import sys

import pytest

from labthings_fastapi.code_generation import (
    NO_ARGUMENTS,
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
        _import_from(name, _name("valid"))


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


def test_python_version_dependence(mocker):
    """Check that we really do need to use different syntax before/after Python 3.12.

    `ast.ClassDef` and `ast.FunctionDef` changed in Python 3.12, so the
    wrapper functions use an if statement to pick the right form.
    Supplying the extra argument doesn't actually cause an error, but MyPy will fail,
    and ignoring the type error will cause MyPy to fail on newer Python versions.

    This test stops a spurious coverage warning.
    It *is* covered because the test suite runs on several versions - but this test
    marks the branch not used by the current Python version as covered.
    """
    if sys.version_info < (3, 12):
        mocker.patch("sys.version_info")
        sys.version_info.__lt__.return_value = False
        cls = _class("MyClass", [], [])
        assert isinstance(cls, ast.ClassDef)
        func = _function("my_func", NO_ARGUMENTS, [], None)
        assert isinstance(func, ast.FunctionDef)
    else:
        mocker.patch("sys.version_info")
        sys.version_info.__lt__.return_value = True
        cls = _class("MyClass", [], [])
        assert isinstance(cls, ast.ClassDef)
        func = _function("my_func", NO_ARGUMENTS, [], None)
        assert isinstance(func, ast.FunctionDef)
