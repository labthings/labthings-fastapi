"""Test thing definitions for type checking.

This module checks that code defining a Thing may be type checked using
mypy.

Note that most of the properties are typed as ``int`` or ``int | None``
and we do not attempt to cover all possible types. A greater range of types
should be tested in code that's actually run, in the `tests` folder. For
this file, what's important is checking that:

1. The type of the default/factory is compatible with the property
    (though not necessarily identical).
2. Errors are raised if types don't match.
3. Class and instance attributes have the expected types.

This requires at least a couple of types, where one is compatible
with the other, hence ``int`` and ``int | None`` which lets us
check compatibility, and also check ``None`` is OK as a default.

See README.md for how it's run.
"""

import labthings_fastapi as lt
from labthings_fastapi.properties import FunctionalProperty

from typing_extensions import assert_type
import typing


def optional_int_factory() -> int | None:
    """Return an optional int."""
    return None


def int_factory() -> int:
    """Return an int."""
    return 0


unbound_prop = lt.property(default=0)
"""A property that is not bound to a Thing.

This will go wrong at runtime if we access its ``model`` but it should
have its type inferred as an `int`. This is intended to let mypy check
the default is of the correct type when used with dataclass-style syntax
(``prop: int = lt.property(default=0)`` ).
"""
assert_type(unbound_prop, int)

unbound_prop_2 = lt.property(default_factory=int_factory)
"""A property that is not bound to a Thing, with a factory.

As with `.unbound_prop` this won't work at runtime, but its type should
be inferred as `int` (which allows checking the default type matches
the attribute type annotation, when used on a class).
"""

assert_type(unbound_prop_2, int)


@lt.property
def strprop(self: typing.Any) -> str:
    """A functional property that should not cause mypy errors."""
    return "foo"


assert_type(strprop, FunctionalProperty[str])


class TestPropertyDefaultsMatch(lt.Thing):
    """A Thing that checks our property type hints are working.

    This Thing defines properties in various ways. Some of these should cause
    mypy to throw errors, for example if the default has the wrong type.
    """

    # These properties should not cause mypy errors, as the default matches
    # the type hint.
    intprop: int = lt.property(default=0)
    optionalintprop: int | None = lt.property(default=None)
    optionalintprop2: int | None = lt.property(default=0)
    optionalintprop3: int | None = lt.property(default_factory=optional_int_factory)
    optionalintprop4: int | None = lt.property(default_factory=int_factory)

    # This property should cause mypy to throw an error, as the default is a string.
    # The type hint is an int, so this should cause a mypy error.
    intprop2: int = lt.property(default="foo")  # type: ignore[assignment]
    intprop3: int = lt.property(default_factory=optional_int_factory)  # type: ignore[assignment]

    # Data properties must always have a default, so this line should fail
    # with mypy. It will also raise an exception at runtime, and there's a
    # test for that run with pytest.
    intprop4: int = lt.property()  # type: ignore[call-overload]
    "This property should cause mypy to throw an error, as it has no default."

    listprop: list[int] = lt.property(default_factory=list)
    """A list property with a default factory.
    
    Note the default factory is a less specific type.
    
    Default types must be compatible with the attribute type, but not 
    necessarily the same. This tests a common scenario, where the default (an
    empty list) is compatible, but not the same as ``list[int]`` .

    Note this is "tested" simply by the absence of `mypy` errors.
    """


# Check that the type hints on an instance of the class are correct.
test_defaults_match = TestPropertyDefaultsMatch()
assert_type(test_defaults_match.intprop, int)
assert_type(test_defaults_match.intprop2, int)
assert_type(test_defaults_match.intprop3, int)
assert_type(test_defaults_match.optionalintprop, int | None)
assert_type(test_defaults_match.optionalintprop2, int | None)
assert_type(test_defaults_match.optionalintprop3, int | None)
assert_type(test_defaults_match.optionalintprop4, int | None)

# NB the types of the class attributes will be the same as the instance attributes
# because of the type hint on `lt.property`. This is incorrect (the class attributes
# will be `DataProperty` instances), but it is not something that code outside of
# LabThings-FastAPI should rely on. See typing notes in `lt.property` docstring
# for more details.


class TestExplicitDescriptor(lt.Thing):
    r"""A Thing that checks our explicit descriptor type hints are working.

    This tests `.DataProperty` descriptors work as intended when used directly,
    rather than via ``lt.property``\ .

    ``lt.property`` has a "white lie" on its return type, which makes it
    work with dataclass-style syntax (type annotation on the class attribute
    rather than part of the descriptor). It's therefore useful to test
    the underlying class as well.
    """

    intprop1 = lt.DataProperty[int](default=0)
    """A DataProperty that should not cause mypy errors."""

    intprop2 = lt.DataProperty[int](default_factory=int_factory)
    """The factory matches the type hint, so this should be OK."""

    intprop3 = lt.DataProperty[int](default_factory=optional_int_factory)
    """Uses a factory function that doesn't match the type hint.
    
    This ought to cause mypy to throw an error, as the factory function can
    return None, but at time of writing this doesn't happen.
    
    This error is caught correctly when called via `lt.property`.
    """

    intprop4 = lt.DataProperty[int](default="foo")  # type: ignore[call-overload]
    """This property should cause an error, as the default is a string."""

    intprop5 = lt.DataProperty[int]()  # type: ignore[call-overload]
    """This property should cause mypy to throw an error, as it has no default."""

    optionalintprop1 = lt.DataProperty[int | None](default=None)
    """A DataProperty that should not cause mypy errors."""

    optionalintprop2 = lt.DataProperty[int | None](default_factory=optional_int_factory)
    """This property should not cause mypy errors: the factory matches the type hint."""

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


Val = typing.TypeVar("Val")


def f_property(getter: typing.Callable[..., Val]) -> FunctionalProperty[Val]:
    """A function that returns a FunctionalProperty with a getter."""
    return FunctionalProperty(getter)


class TestFunctionalProperty(lt.Thing):
    """A Thing that checks our functional property type hints are working."""

    @lt.property
    def intprop1(self) -> int:
        """A functional property that should not cause mypy errors."""
        return 0

    @lt.property
    def intprop2(self) -> int:
        """This property should not cause mypy errors and is writeable.

        This property has a getter and setter, so it can be read and written
        from other code within the Thing. However, we make it read-only for
        client code (over HTTP or a DirectThingClient).
        """
        return 0

    @intprop2.setter
    def set_intprop2(self, value: int) -> None:
        """Setter for intprop2."""
        pass

    # Make the property read-only in the Thing Description and for HTTP
    # clients, or DirectThingClients. See property documentation on
    # readthedocs for examples.
    intprop2.readonly = True

    @lt.property
    def intprop3(self) -> int:
        """This getter is fine, but the setter should fail type checking."""
        return 0

    @intprop3.setter
    def set_intprop3(self, value: str) -> None:
        """Setter for intprop3. It's got the wrong type so should fail."""
        pass

    @f_property
    def fprop(self) -> int:
        """A functional property that should not cause mypy errors.

        This uses a much simpler function than ``lt.property`` to check
        the behaviour is the same.
        """
        return 0

    @fprop.setter
    def set_fprop(self, value: int) -> None:
        """Setter for fprop. Type checking should pass."""
        pass

    @lt.property
    def strprop(self) -> str:
        """A property with identically named getter/setter."""
        return "Hello world!"

    @strprop.setter  # type: ignore[no-redef]
    def strprop(self, val: str) -> None:
        """A setter with the same name as the getter.

        This is the convention for `builtins.property` but `mypy` does not
        allow it for any other property-like decorators.

        This function should raise a ``no-redef`` error.
        """
        pass


assert_type(TestFunctionalProperty.intprop1, FunctionalProperty[int])
assert_type(TestFunctionalProperty.intprop2, FunctionalProperty[int])
assert_type(TestFunctionalProperty.intprop3, FunctionalProperty[int])
assert_type(TestFunctionalProperty.fprop, FunctionalProperty[int])
# Don't check ``strprop`` because it caused an error and thus will
# not have the right type, even though the error is ignored.

test_functional_property = TestFunctionalProperty()
assert_type(test_functional_property.intprop1, int)
assert_type(test_functional_property.intprop2, int)
assert_type(test_functional_property.intprop3, int)
assert_type(test_functional_property.fprop, int)
# ``strprop`` will be ``Any`` because of the ``[no-redef]`` error.
