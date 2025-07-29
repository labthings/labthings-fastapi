"""Test thing definitions for type checking.

This module checks that code defining a Thing may be type checked using
mypy.

See README.md for more details.
"""

import labthings_fastapi as lt

from typing import assert_type


def optional_int_factory() -> int | None:
    """Return an optional int."""
    return None


def int_factory() -> int:
    """Return an int."""
    return 0


class TestPropertyDefaultsMatch(lt.Thing):
    """A Thing that checks our property type hints are working.

    This Thing defines properties in various ways. Some of these should cause
    mypy to throw errors, for example if the default has the wrong type.
    """

    # These properties should not cause mypy errors, as the default matches
    # the type hint.
    intprop: int = lt.property(0)
    optionalintprop: int | None = lt.property(None)
    optionalintprop2: int | None = lt.property(0)
    optionalintprop3: int | None = lt.property(default_factory=optional_int_factory)

    # This property should cause mypy to throw an error, as the default is a string.
    # The type hint is an int, so this should cause a mypy error.
    intprop2: int = lt.property("foo")  # type: ignore[assignment]
    intprop3: int = lt.property(default_factory=optional_int_factory)  # type: ignore[assignment]

    # Data properies must always have a default, so this line should fail
    # with mypy. It will also raise an excetion at runtime, and there's a
    # test for that run with pytest.
    intprop4: int = lt.property()  # type: ignore[call-overload]
    "This property should cause mypy to throw an error, as it has no default."

    listprop: list[int] = lt.property(default_factory=list)
    "A list property with a default factory. Note the default factory is a less specific type."


# Check that the type hints on an instance of the class are correct.
test_defaults_match = TestPropertyDefaultsMatch()
assert_type(test_defaults_match.intprop, int)
assert_type(test_defaults_match.intprop2, int)
assert_type(test_defaults_match.intprop3, int)
assert_type(test_defaults_match.optionalintprop, int | None)
assert_type(test_defaults_match.optionalintprop2, int | None)
assert_type(test_defaults_match.optionalintprop3, int | None)

# NB the types of the class attributes will be the same as the instance attributes
# because of the type hint on `lt.property`. This is incorrect (the class attributes
# will be `DataProperty` instances), but it is not something that code outside of
# LabThings-FastAPI should rely on. See typing notes in `lt.property` docstring
# for more details.


class TestExplicitDescriptor(lt.Thing):
    """A Thing that checks our explicit descriptor type hints are working."""

    intprop1 = lt.DataProperty[int](0)
    """A DataProperty that should not cause mypy errors."""

    intprop2 = lt.DataProperty[int](default_factory=int_factory)
    """This property should not cause mypy errors, as the factory matches the type hint."""

    intprop3 = lt.DataProperty[int](default_factory=optional_int_factory)
    """Uses a factory function that doesn't match the type hint.
    
    This ought to cause mypy to throw an error, as the factory function can
    return None, but at time of writing this doesn't happen.
    
    This error is caught correctly when called via `lt.property`.
    """

    intprop4 = lt.DataProperty[int]("foo")  # type: ignore[call-overload]
    """This property should cause mypy to throw an error, as the default is a string."""

    intprop5 = lt.DataProperty[int]()  # type: ignore[call-overload]
    """This property should cause mypy to throw an error, as it has no default."""

    optionalintprop1 = lt.DataProperty[int | None](None)
    """A DataProperty that should not cause mypy errors."""

    optionalintprop2 = lt.DataProperty[int | None](default_factory=optional_int_factory)
    """This property should not cause mypy errors, as the factory matches the type hint."""

    optionalintprop3 = lt.DataProperty[int | None](default_factory=int_factory)
    """Uses a factory function that is a subset of the type hint."""


# Check instance attributes are typed correctly.
test_explicit_descriptor = TestExplicitDescriptor()
assert_type(test_explicit_descriptor.intprop1, int)
assert_type(test_explicit_descriptor.intprop2, int)
assert_type(test_explicit_descriptor.intprop3, int)

assert_type(test_explicit_descriptor.optionalintprop1, int | None)
assert_type(test_explicit_descriptor.optionalintprop2, int | None)
assert_type(test_explicit_descriptor.optionalintprop3, int | None)

# Check class attributes are typed correctly.
assert_type(TestExplicitDescriptor.intprop1, lt.DataProperty[int])
assert_type(TestExplicitDescriptor.intprop2, lt.DataProperty[int])
assert_type(TestExplicitDescriptor.intprop3, lt.DataProperty[int])

assert_type(TestExplicitDescriptor.optionalintprop1, lt.DataProperty[int | None])
assert_type(TestExplicitDescriptor.optionalintprop2, lt.DataProperty[int | None])
assert_type(TestExplicitDescriptor.optionalintprop3, lt.DataProperty[int | None])


class TestFunctionalProperty(lt.Thing):
    """A Thing that checks our functional property type hints are working."""

    @lt.property
    def intprop1(self) -> int:
        """A functional property that should not cause mypy errors."""
        return 0

    @lt.property
    def intprop2(self) -> int:
        """This property should not cause mypy errors and is writeable."""
        return 0

    @intprop2.setter
    def intprop2(self, value: int):
        """Setter for intprop2."""
        pass

    intprop2.readonly = True  # This should be an OK thing to do.

    @lt.property
    def intprop3(self) -> int:
        """Cause mypy to throw an error as the setter is wrongly typed."""
        return 0

    @intprop3.setter
    def intprop3(self, value: str):
        """Setter for intprop3."""
        pass
