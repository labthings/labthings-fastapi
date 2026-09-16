"""Computed properties.

A computed property is like a functional property, but it only depends on
properties which are observable.
This means LabThings is able to recompute
it whenever its dependencies change, allowing it to be observed.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Generic, cast
from weakref import WeakKeyDictionary

from anyio import create_memory_object_stream
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

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
        self._streams: WeakKeyDictionary[
            "Thing",
            tuple[MemoryObjectSendStream[Message], MemoryObjectReceiveStream[Message]],
        ] = WeakKeyDictionary()

    @property
    def is_computed(self) -> bool:
        """Whether the property is a computed property."""
        return True

    def instance_get(self, obj: Owner) -> Value:
        """Get the value of this functional property.

        :param obj: the object on which this property is being accessed.
        :return: the value of the property.
        """
        dependencies: set[str] = set()
        wrapper = access_wrapper(obj, dependencies=dependencies)
        val = self._fget(wrapper)
        if not dependencies:
            self._stop_watching(obj)
        else:
            self._watch_for_changes(obj, dependencies)
        return val

    def _watch_for_changes(self, obj: Owner, dependencies: set[str]) -> None:
        """Ensure a coroutine is watching for changes.

        This method will check whether we are currently processing messages
        from the properties we depend on, so that this property will be
        recomputed when they change. If that's not happening, we will start
        a new coroutine to do this.

        :param obj: the object on which the property is defined.
        :param dependencies: the properties on which the object depends.
        :raises ValueError: if the dependencies set is empty.
        """
        if not dependencies:
            # This shouldn't ever happen - the calling function checks that
            # dependencies is non-empty.
            raise ValueError(
                "_watch_for_changes must have at least one dependency to watch."
            )
        streams = self._streams.get(obj)
        if streams is None or streams[1].statistics().open_receive_streams == 0:
            # If the streams are missing or closed, create them and start the coroutine.
            send, recv = create_memory_object_stream[Message]()
            obj._thing_server_interface.start_async_task_soon(
                _recompute_on_changes, self.descriptor_info().publish, recv
            )
            self._streams[obj] = send, recv
        else:
            send, recv = self._streams[obj]

        # The streams exist and a coroutine is monitoring them. Now, subscribe
        # to changes in our dependencies
        for affordance in dependencies:
            obj._thing_server_interface.subscribe(obj.name, affordance, send)
        # Unsubscribe from any dependencies no longer needed
        for affordance in self._dependencies[obj].difference(dependencies):
            obj._thing_server_interface.unsubscribe(obj.name, affordance, send)
        self._dependencies[obj] = dependencies

    def _stop_watching(self, obj: Owner) -> None:
        """Stop watching for changes, as we have no dependencies.

        :param obj: the Thing on which we are defined.
        """
        send, _recv = self._streams[obj]
        # Unsubscribe from any dependencies no longer needed
        for affordance in self._dependencies[obj]:
            obj._thing_server_interface.unsubscribe(obj.name, affordance, send)
        # Close the stream, so that the coroutine terminates
        send.close()


async def _recompute_on_changes(
    recompute: Callable[[], None], stream: MemoryObjectReceiveStream[Message]
) -> None:
    """Recompute and publish a property if its dependencies change.

    :param recompute: a function to call when a dependency changes.
    :param stream: the stream on which we'll get notified.
    """
    async for _msg in stream:
        # Currently, we don't check what changed - we just trigger a recompute.
        recompute()


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
            prop.publish()
