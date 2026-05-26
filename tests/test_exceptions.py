"""Test code for exceptions.

There's not much code to test in the exceptions module: currently just the logic that
adds user code details to certain errors.
"""

import pytest

from labthings_fastapi import exceptions


EXCEPTIONS = (
    exceptions.InvalidReturnValueError,
    exceptions.UnserialisableTypeError,
    exceptions.CausedByUserCodeError,
)


def example_function():
    """An example function."""


class ExampleClass:
    """An example class with a property."""

    prop: int = 0


@pytest.mark.parametrize("cls", EXCEPTIONS)
@pytest.mark.parametrize("args", [("message",), ("arg_1", "arg_2")])
def test_appending_exception_data(cls, args):
    """Check that we can append user code to an exception."""
    exc: exceptions.CausedByUserCodeError = cls(*args)
    exc.set_source_class(ExampleClass)
    assert "test_exceptions.ExampleClass" in str(exc)

    exc: exceptions.CausedByUserCodeError = cls(*args)
    exc.set_source_class(ExampleClass, "prop")
    assert "test_exceptions.ExampleClass.prop" in str(exc)

    exc: exceptions.CausedByUserCodeError = cls(*args)
    exc.set_source_function(example_function)
    file = example_function.__code__.co_filename
    line = example_function.__code__.co_firstlineno
    assert file.endswith("test_exceptions.py")
    assert isinstance(line, int)
    assert f"{file}:{line}" in str(exc)
    assert "example_function" in str(exc)
