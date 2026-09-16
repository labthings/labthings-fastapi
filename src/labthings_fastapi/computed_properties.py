"""Computed properties.

A computed property is like a functional property, but it only depends on
properties which are observable.
This means LabThings is able to recompute
it whenever its dependencies change, allowing it to be observed.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, cast

from anyio import create_memory_object_stream
from anyio.streams.memory import MemoryObjectSendStream

from labthings_fastapi.exceptions import PropertyNotObservableError
from labthings_fastapi.message_broker import Message
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

    def __setattr__(self, name: str, value: Any) -> None:
        """Don't allow attributes to be set, there should be no side-effects.

        :param name: the name of the attribute.
        :param value: the value to set.
        :raises AttributeError: because the wrapper is read-only.
        """
        raise AttributeError("Computed properties may not set values.")


def access_wrapper(obj: Owner, dependencies: set[str]) -> Owner:
    """Wrap a Thing to record attribute access.

    This function is preferred to instantiating AccessWrapper directly,
    as it ensures the wrapper is type hinted as the original object.

    :param obj: the Thing to wrap.
    :param dependencies: a set to store dependencies.
    :return: `obj` with an attribute access wrapper.
    """
    # Typing note: AccessWrapper proxies attribute access back to the
    # wrapped object, so its signature should be identical to `obj`
    # and thus the `cast` below is justified.
    wrapper = AccessWrapper(obj, dependencies=dependencies)
    return cast(Owner, wrapper)


class ComputedProperty(FunctionalProperty[Owner, Value], Generic[Owner, Value]):
    """A property that recomputes its value on demand.

    This is a way to make functional properties observable.
    """

    @property
    def is_computed(self) -> bool:
        """Whether the property is a computed property."""
        return True

    def instance_get(self, obj: Owner, dependencies: set[str] | None = None) -> Value:
        """Get the value of this functional property.

        :param obj: the object on which this property is being accessed.
        :param dependencies: an optional set to be populated with properties accessed
            during recomputation.
        :return: the value of the property.
        """
        if dependencies is not None:
            wrapper = access_wrapper(obj, dependencies=dependencies)
            return self._fget(wrapper)
        else:
            return self._fget(obj)

    async def _watch_for_changes(self, obj: Owner) -> None:
        """Watch for changes in our dependencies, and recompute as needed.

        This method will evaluate the computed property, tracking which
        properties are accessed. It then subscribes to these properties,
        and will recompute the property as required.

        :param obj: the object on which the property is defined.
        """
        send, recv = create_memory_object_stream[Message](max_buffer_size=1)
        # Subscribe to a non-existent affordance, to ensure that the stream
        # is closed by the message broker even if there are no other
        # subscriptions.
        obj._thing_server_interface.subscribe(obj.name, "#dummy", send)

        dependencies: set[str] = set()
        # Add a message to the stream, so we initialise everything immediately
        # in the `async for` loop.
        initial_message = Message(obj.name, self.name, "property", None)
        await send.send(initial_message)

        # Whenever a dependency changes, we'll recompute and publish an update
        async for message in recv:
            old_dependencies = dependencies
            dependencies = set()
            value = self.instance_get(obj, dependencies=dependencies)
            await self._update_subscriptions(obj, dependencies, old_dependencies, send)
            if message is initial_message:
                continue
            obj._thing_server_interface.publish(
                Message(obj.name, self.name, "property", value)
            )

    @staticmethod
    async def _update_subscriptions(
        obj: Owner,
        dependencies: set[str],
        old_dependencies: set[str],
        send_stream: MemoryObjectSendStream[Message],
    ) -> None:
        """Subscribe and unsubscribe to other properties.

        :param obj: the Thing on which we are defined.
        :param dependencies: a set of the names of current dependencies.
        :param old_dependencies: previous dependencies - any not in ``dependencies``
            will be unsubscribed.
        :param send_stream: the stream to use for subscriptions.
        """
        # The streams exist and a coroutine is monitoring them. Now, subscribe
        # to changes in our dependencies
        for affordance in dependencies:
            obj._thing_server_interface.subscribe(obj.name, affordance, send_stream)
        # Unsubscribe from any dependencies no longer needed
        for affordance in old_dependencies.difference(dependencies):
            obj._thing_server_interface.unsubscribe(obj.name, affordance, send_stream)


def computed_property(fget: Callable[[Owner], Value]) -> ComputedProperty[Owner, Value]:
    """Decorate a method as a computed property.

    :param fget: the getter function, which must depend only on observable properties.
    :return: a computed property descriptor.
    """
    return ComputedProperty(fget=fget)


def initialise_computed_properties(thing: "Thing") -> None:
    """Initialise the computed properties on a Thing.

    :param thing: the Thing on which to initialise computed properties.
    """
    for prop in thing.properties.values():
        if prop.is_computed:
            computed_property = prop.get_descriptor()
            if not isinstance(computed_property, ComputedProperty):
                continue
            thing._thing_server_interface.start_async_task_soon(
                computed_property._watch_for_changes, thing
            )
