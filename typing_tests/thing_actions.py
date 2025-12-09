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
# The lines below create an instance, then check each of the four actions
# has the correct input parameters and return type.
# Note that this test will fail if there are unused ignores, so the
# lines with ignore comments assert that errors are raised.
thing = create_thing_without_server(ThingWithActions)

# Check the function returns the expected type, when called with the expected args
assert_type(thing.no_args_no_return(), None)
# Check that using arguments causes mypy to raise an error.
thing.no_args_no_return("arg")  # type: ignore[call-arg]
thing.no_args_no_return(unexpected=123)  # type: ignore[call-arg]

# Check the return type is None, when called with the expected args
assert_type(thing.with_args_no_return(1, "test"), None)
# Check that missing arguments are caught by mypy
thing.with_args_no_return()  # type: ignore[call-arg]
# Check that wrong argument types are caught by mypy
thing.with_args_no_return(1, 2)  # type: ignore[arg-type]

# Check the return type is correct when called without arguments
assert_type(thing.no_args_with_return(), float)
# Check that using arguments causes mypy to raise an error.
thing.with_args_no_return("unexpected")  # type: ignore[arg-type, call-arg]
thing.with_args_no_return(unexpected=123)  # type: ignore[call-arg]

# Check the return type is correct when called with the expected args
assert_type(thing.with_args_with_return(10, "data"), float)
# Check that missing arguments are caught by mypy
thing.with_args_no_return()  # type: ignore[call-arg]
# Check that wrong argument types are caught by mypy
thing.with_args_no_return(10, 20)  # type: ignore[arg-type]


# We should also make sure the attribute is a correctly-typed descriptor
assert_type(
    ThingWithActions.no_args_no_return, ActionDescriptor[[], None, ThingWithActions]
)
# assert_type doesn't work well with the ParamSpec for arguments, so we use an
# assignment instead to check the type is compatible.
with_args_no_return_descriptor: ActionDescriptor[[int, str], None, ThingWithActions] = (
    ThingWithActions.with_args_no_return
)
assert_type(
    ThingWithActions.no_args_with_return, ActionDescriptor[[], float, ThingWithActions]
)
with_args_with_return_descriptor: ActionDescriptor[
    [int, str], float, ThingWithActions
] = ThingWithActions.with_args_with_return

# Check the documentation-related properties are correctly typed
# There's no need to check all four actions here, as they should all be the same.
assert_type(ThingWithActions.with_args_with_return.__doc__, str | None)
assert_type(ThingWithActions.with_args_with_return.description, str | None)
assert_type(ThingWithActions.with_args_with_return.title, str)
assert_type(ThingWithActions.with_args_with_return.name, str)
