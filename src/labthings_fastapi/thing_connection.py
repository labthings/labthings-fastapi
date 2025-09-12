r"""Facilitate connections between Things.

It is often desirable for two Things in the same server to be able to communicate.
In order to do this in a nicely typed way that is easy to test and inspect,
LabThings-FastAPI provides the `.thing_connection`\ . This allows a `.Thing`
to declare that it depends on another `.Thing` being present, and provides a way for
the server to automatically connect the two when the server is set up.

Thing connections are set up **after** all the `.Thing` instances are initialised.
This means you should not rely on them during initialisation: if you attempt to
access a connection before it is provided, it will raise an exception. The
advantage of making connections after initialisation is that circular connections
are not a problem: Thing `a` may depend on Thing `b` and vice versa.

As with properties, thing connections will usually be declared using the function
`.thing_connection` rather than the descriptor directly. This allows them to be
typed and documented on the class, i.e.

.. code-block:: python

    import labthings_fastapi as lt


    class ThingA(lt.Thing):
        "A class that doesn't do much."

        @lt.action
        def say_hello(self) -> str:
            "A canonical example function."
            return "Hello world."


    class ThingB(lt.Thing):
        "A class that relies on ThingA."

        thing_a: ThingA = lt.thing_connection()

        @lt.action
        def say_hello(self) -> str:
            "I'm too lazy to say hello, ThingA does it for me."
            return self.thing_a.say_hello()
"""

from typing import Generic, TypeVar, TYPE_CHECKING
from weakref import WeakKeyDictionary, ref
from .base_descriptor import FieldTypedBaseDescriptor
from .exceptions import ThingNotConnectedError

if TYPE_CHECKING:
    from .thing import Thing


ThingSubclass = TypeVar("ThingSubclass", bound=Thing)


class ThingConnection(Generic[ThingSubclass], FieldTypedBaseDescriptor[ThingSubclass]):
    """A descriptor that returns an instance of a Thing from this server.

    Thing connections allow `.Thing` instances to access other `.Thing` instances
    in the same LabThings server.
    """

    def __init__(self, *, default_path: str | None = None) -> None:
        """Declare a ThingConnection.

        :param default_name: The name of the Thing that will be connected by default.
        """
        self._default_path = default_path
        self._things: WeakKeyDictionary[Thing, ref[ThingSubclass]] = WeakKeyDictionary()

    def connect_thing(self, host_thing: Thing, connected_thing: ThingSubclass) -> None:
        r"""Connect a `.Thing` to a `.ThingConnection`\ .

        This method sets up a ThingConnection on ``host_thing`` such that it will
        supply ``connected_thing`` when accessed.
        """
        if not isinstance(connected_thing, self.value_type):
            msg = (
                f"Can't connect {connected_thing} to {host_thing}.{self.name}. "
                f"This ThingConnection must be of type {self.value_type}."
            )
            raise TypeError(msg)
        self._things[host_thing] = ref(connected_thing)

    def instance_get(self, obj: Thing) -> ThingSubclass:
        r"""Supply the connected `.Thing`\ .

        :raises ThingNotConnectedError: if the ThingConnection has not yet been set up.
        """
        try:
            thing_ref = self._things[obj]
            return thing_ref()
        except KeyError as e:
            msg = f"{self.name} has not been connected to a Thing yet."
            raise ThingNotConnectedError(msg) from e
        # Note that ReferenceError is deliberately not handled: the Thing
        # referred to by thing_ref should exist until the server has shut down.

    def __set__(self, obj: Thing, value: ThingSubclass) -> None:
        """Raise an error as this is a read-only descriptor.

        :param obj: the `.Thing` on which the descriptor is defined.
        :param value: the value being assigned.

        :raises AttributeError: this descriptor is not writeable.
        """
        raise AttributeError("This descriptor is read-only.")
