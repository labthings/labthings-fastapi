"""Computed properties.

A computed property is like a functional property, but it only depends on
properties which are observable.
This means LabThings is able to recompute
it whenever its dependencies change, allowing it to be observed.
"""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Generic, cast
from weakref import WeakKeyDictionary

from anyio import create_memory_object_stream, to_thread
from anyio.abc import TaskGroup, TaskStatus
from anyio.streams.memory import MemoryObjectSendStream
from typing_extensions import Literal

from labthings_fastapi.exceptions import PropertyNotObservableError
from labthings_fastapi.message_broker import Message
from labthings_fastapi.properties import FunctionalProperty, Owner, Value

if TYPE_CHECKING:
    from labthings_fastapi.thing import Thing


RECOMPUTE = object()


class AccessWrapper:
    """Wrap access to the properties of an object."""

    _access_wrapper_locked = False

    def __init__(self, obj: "Thing", dependencies: set[str]) -> None:
        """Initialise the AccessWrapper.

        :param obj: the object being wrapped.
        :param dependencies: a set to use for tracking dependencies.
        """
        self._obj = obj
        self._dependencies = dependencies
        self._access_wrapper_locked = True

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
        """Don't allow attributes to be set.

        Once the wrapper is initialised, it won't allow attributes to be set.
        We need to be able to set some attributes during `__init__`, but
        after that, everything becomes read-only.

        :param name: the name of the attribute.
        :param value: the value to set.
        :raises AttributeError: because the wrapper is read-only.
        """
        if self._access_wrapper_locked is True:
            raise AttributeError("Computed properties may not set values.")
        super().__setattr__(name, value)


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
        constraints: Mapping[str, Any] | None = None,
        use_global_lock: Literal[False] | None = None,
    ) -> None:
        """Set up a FunctionalProperty.

        Create a descriptor for a property that uses a getter function.

        This class also inherits from `builtins.property` to help type checking
        tools understand that it functions like a property.

        :param fget: the getter function, called when the property is read.
        :param constraints: is passed as keyword arguments to `pydantic.Field`
            to add validation constraints to the property. See `pydantic.Field`
            for details.
        :param use_global_lock: may be set to `False` to disable the global lock
            for setting this property. By default, if global locking is enabled,
            we hold the global lock while setting the property.
        """
        super().__init__(
            fget=fget, constraints=constraints, use_global_lock=use_global_lock
        )
        self._send_streams = WeakKeyDictionary[
            "Thing", MemoryObjectSendStream[Message]
        ]()
        self._latest_values = WeakKeyDictionary["Thing", Value]()

    @property
    def is_computed(self) -> bool:
        """Whether the property is a computed property."""
        return True

    def instance_get(self, obj: Owner) -> Value:
        """Get the value of this computed property.

        This will use the latest value that was cached. It will fall back to
        computing it directly if a cached value is not available.

        :param obj: the object on which this property is being accessed.
        :return: the value of the property.
        """
        try:
            return self._latest_values[obj]
        except KeyError:
            msg = f"Computed property {self.name} was accessed before initialisation."
            obj.logger.warning(msg)
            return self.fget(obj)

    async def _request_recomputation(self, obj: Owner) -> Value:
        """Trigger a recomputation of the property and return the new value.

        :param obj: the object on which the property is defined.
        :return: the value of the property.
        """
        broker = obj._thing_server_interface.message_broker
        send, recv = create_memory_object_stream[Message](max_buffer_size=1)
        # Subscribe for updates (get the recomputed value)
        await broker.subscribe(obj.name, self.name, send)
        # Trigger a recompute
        await self._send_streams[obj].send(
            # Note that RECOMPUTE messages should never hit the broker: they
            # are only ever sent directly to our stream.
            Message(obj.name, self.name, "property", RECOMPUTE)
        )
        message = await recv.receive()
        return message.payload

    def recompute(self, obj: Owner) -> tuple[Value, set[str]]:
        """Recompute the property and track dependencies.

        This function isn't async, and is intended to be called in a
        worker thread.

        :param obj: the object on which the property is defined.
        :return: a tuple of the new value and the dependencies.
        """
        dependencies: set[str] = set()
        wrapper = access_wrapper(obj, dependencies=dependencies)
        value = self._fget(wrapper)
        return value, dependencies

    async def _watch_for_changes(self, obj: Owner, task_status: TaskStatus) -> None:
        """Watch for changes in our dependencies, and recompute as needed.

        This method will evaluate the computed property, tracking which
        properties are accessed. It then subscribes to these properties,
        and will recompute the property as required.

        :param obj: the object on which the property is defined.
        :param task_status: anyio handle that reports when this task has
            started (i.e. once we've figured out dependencies and started
            listening).
        """
        broker = obj._thing_server_interface.message_broker
        send, recv = create_memory_object_stream[Message](max_buffer_size=1)
        # Subscribe to a non-existent affordance, to ensure that the stream
        # is closed by the message broker when it's shut down even if there
        # are no other subscriptions.
        await broker.subscribe(obj.name, "#dummy", send)
        # Save the send stream so other methods can trigger updates
        self._send_streams[obj] = send

        dependencies: set[str] = set()
        # Add a message to the stream, so we initialise everything immediately
        # in the `async for` loop.
        initial_message = Message(obj.name, self.name, "property", RECOMPUTE)
        await send.send(initial_message)

        # Whenever a dependency changes, we'll recompute and publish an update
        async for message in recv:
            old_dependencies = dependencies
            value, dependencies = await to_thread.run_sync(self.recompute, obj)
            await self._update_subscriptions(obj, dependencies, old_dependencies, send)
            if message is initial_message:
                # At this point, we've calculated our dependencies and started
                # listening, so we signal that everything's started OK.
                task_status.started()
                continue
            await broker.publish(Message(obj.name, self.name, "property", value))

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
        broker = obj._thing_server_interface.message_broker
        # The streams exist and a coroutine is monitoring them. Now, subscribe
        # to changes in our dependencies
        for affordance in dependencies:
            await broker.subscribe(obj.name, affordance, send_stream)
        # Unsubscribe from any dependencies no longer needed
        for affordance in old_dependencies.difference(dependencies):
            await broker.unsubscribe(obj.name, affordance, send_stream)


def computed_property(fget: Callable[[Owner], Value]) -> ComputedProperty[Owner, Value]:
    """Decorate a method as a computed property.

    :param fget: the getter function, which must depend only on observable properties.
    :return: a computed property descriptor.
    """
    return ComputedProperty(fget=fget)


async def start_watching_computed_properties(
    thing: "Thing",
    task_group: TaskGroup,
) -> None:
    """Watch the computed properties on a Thing.

    :param thing: the Thing on which to watch computed properties.
    :param task_group: the task group to use for watching properties.
    :raises TypeError: if a property declares itself to be computed, but is not
        an instance of ComputedProperty.
    """
    for prop in thing.properties.values():
        if prop.is_computed:
            computed_property = prop.get_descriptor()
            if not isinstance(computed_property, ComputedProperty):
                msg = "Computed properties must be instances of ComputedProperty."
                raise TypeError(msg)
            await task_group.start(computed_property._watch_for_changes, thing)
