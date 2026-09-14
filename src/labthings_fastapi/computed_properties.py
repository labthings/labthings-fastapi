"""Computed properties.

A computed property is like a functional property, but it only depends on
properties which are observable.
This means LabThings is able to recompute
it whenever its dependencies change, allowing it to be observed.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic
from weakref import WeakKeyDictionary

from labthings_fastapi.exceptions import PropertyNotObservableError
from labthings_fastapi.properties import FunctionalProperty, Owner, Value

if TYPE_CHECKING:
    from labthings_fastapi.thing import Thing


class AccessWrapper:
    """Wrap access to the properties of an object."""

    def __init__(self, obj: "Thing", dependencies: set[str]) -> None:
        """Initialise the AccessWrapper.

        :param obj: the object being wrapped.
        :param dependencies: a set to use for tracking dependencies.
        """
        self._obj = obj
        self._dependencies = dependencies

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to the underlying object.

        :param name: The name of the attribute being accessed.
        :return: The value of the object.
        :raises PropertyNotObservableError: if a non-observable property
            is accessed.
        :raises TypeError: if something other than a property is accessed.
        """
        if name in self._obj.properties:
            if self._obj.properties[name].is_observable:
                self._dependencies.add(name)
                print(f"Found an access to {name}")
                return getattr(self._obj, name)
            else:
                raise PropertyNotObservableError(
                    f"{self._obj.name}.{name} is not observable. "
                    "Only observable properties may be accessed from a "
                    "computed property."
                )
        else:
            raise TypeError(
                f"{self._obj.name}.{name} is not a property. "
                "Only observable properties may be accessed from a "
                "computed property."
            )


class ComputedProperty(FunctionalProperty[Owner, Value], Generic[Owner, Value]):
    """A property that recomputes its value on demand.

    This is a way to make functional properties observable.
    """

    def __init__(
        self,
        fget: Callable[[Owner], Value],
        **kwargs: Any,
    ) -> None:
        r"""Initialise a computed property.

        :param fget: The getter function.
        :param \**kwargs: Additional keyword arguments are passed to
            `BaseProperty`.
        """
        super().__init__(fget=fget, **kwargs)
        self._dependencies: "WeakKeyDictionary[Thing, set[str]]" = WeakKeyDictionary()

    def instance_get(self, obj: Owner) -> Value:
        """Get the value of this functional property.

        :param obj: the object on which this property is being accessed.
        :return: the value of the property.
        """
        dependencies: set[str] = set()
        access_wrapper = AccessWrapper(obj, dependencies=dependencies)
        # access_wrapper is wrapping `self` but has its own type. We therefore
        # ignore type checking on this line.
        val = self._fget(access_wrapper)  # type: ignore[arg-type]
        self._dependencies[obj] = dependencies
        return val


def computed_property(fget: Callable[[Owner], Value]) -> ComputedProperty[Owner, Value]:
    """Decorate a method as a computed property.

    :param fget: the getter function, which must depend only on observable properties.
    :return: a computed property descriptor.
    """
    return ComputedProperty(fget=fget)
