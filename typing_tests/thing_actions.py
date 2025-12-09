"""Check actions are typed correctly.

This module will be checked by `mypy` and is intended to ensure that methods
decorated as `lt.action` have the correct type signatures.
"""

import labthings_fastapi as lt
from labthings_fastapi.actions import ActionDescriptor

from typing_extensions import assert_type

from labthings_fastapi.testing import create_thing_without_server


class ThingWithActions(lt.Thing):
    """A Thing with various actions for testing."""

    @lt.action
    def no_args_no_return(self) -> None:
        """An action with no arguments and no return value."""
        pass

    @lt.action
    def with_args_no_return(self, x: int, y: str) -> None:
        """An action with arguments and no return value."""
        pass

    @lt.action
    def no_args_with_return(self) -> float:
        """An action with no arguments and a return value."""
        return 3.14

    @lt.action
    def with_args_with_return(self, a: int, b: str) -> float:
        """An action with arguments and a return value."""
        return 3.14


# What we really care about is that the instance attributes are right.
thing = create_thing_without_server(ThingWithActions)

assert_type(thing.no_args_no_return(), None)
thing.no_args_no_return("arg")  # type: ignore[arg-type]
thing.no_args_no_return(unexpected=123)  # type: ignore[arg-type]

assert_type(thing.with_args_no_return(1, "test"), None)
thing.with_args_no_return()  # type: ignore[arg-type]
thing.with_args_no_return(1, 2)  # type: ignore[arg-type]

assert_type(thing.no_args_with_return(), float)
thing.with_args_no_return("unexpected")  # type: ignore[arg-type]
thing.with_args_no_return(unexpected=123)  # type: ignore[arg-type]

assert_type(thing.with_args_with_return(10, "data"), float)
thing.with_args_no_return()  # type: ignore[arg-type]
thing.with_args_no_return(10, 20)  # type: ignore[arg-type]


# We should also make sure the attribute is a descriptor
assert_type(ThingWithActions.no_args_no_return, ActionDescriptor)
assert_type(ThingWithActions.with_args_no_return, ActionDescriptor)
assert_type(ThingWithActions.no_args_with_return, ActionDescriptor)
assert_type(ThingWithActions.with_args_with_return, ActionDescriptor)

# Pick any one and check for the documentation-related properties
assert_type(ThingWithActions.with_args_with_return.__doc__, str | None)
assert_type(ThingWithActions.with_args_with_return.description, str | None)
assert_type(ThingWithActions.with_args_with_return.title, str)
assert_type(ThingWithActions.with_args_with_return.name, str)
