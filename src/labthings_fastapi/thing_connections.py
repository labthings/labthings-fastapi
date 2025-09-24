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

from types import EllipsisType, NoneType, UnionType
from typing import Any, Generic, TypeVar, TYPE_CHECKING, Union, get_args, get_origin
from collections.abc import Mapping, Sequence
from weakref import ReferenceType, WeakKeyDictionary, ref, WeakValueDictionary
from .base_descriptor import FieldTypedBaseDescriptor
from .exceptions import ThingNotConnectedError, ThingConnectionError

if TYPE_CHECKING:
    from .thing import Thing


ThingSubclass = TypeVar("ThingSubclass", bound="Thing")
ConnectedThings = TypeVar(
    "ConnectedThings",
    bound="Mapping[str, Thing] | Thing | None",
)


class ThingConnection(
    Generic[ConnectedThings], FieldTypedBaseDescriptor[ConnectedThings]
):
    r"""Descriptor that returns other Things from the server.

    A `.ThingConnection` provides either one or several
    `.Thing` instances as a property of a `.Thing`\ . This allows `.Thing`\ s
    to communicate with each other within the server, including accessing
    attributes that are not exposed over HTTP.

    While it is possible to dynamically retrieve a `.Thing` from the `.ThingServer`
    this is not recommended: using Thing Connections ensures all the `.Thing`
    instances are available before the server starts, reducing the likelihood
    of run-time crashes.

    The usual way of creating these connections is the function
    `.thing_connection`\ . This class and its subclasses are not usually
    instantiated directly.

    The type of the `.ThingConnection` attribute is key to its operation.
    It should be assigned to an attribute typed either as a `.Thing` subclass,
    a mapping of strings to `.Thing` or subclass instances, or an optional
    `.Thing` instance:

    .. code-block:: python

        class OtherExample(lt.Thing):
            pass


        class Example(lt.Thing):
            # This will always evaluate to an `OtherExample`
            other_thing: OtherExample = lt.thing_connection("other_thing")

            # This may evaluate to an `OtherExample` or `None`
            optional: OtherExample | None = lt.thing_connection("other_thing")

            # This evaluates to a mapping of `str` to `.Thing` instances
            things: Mapping[str, OtherExample] = lt.thing_connection(["thing_a"])
    """

    def __init__(
        self, *, default: str | None | Sequence[str] | EllipsisType = ...
    ) -> None:
        """Declare a ThingConnection.

        :param default: The name of the Thing(s) that will be connected by default.

            If the type is optional (e.g. ``ThingSubclass | None``) a default
            value of ``None`` will result in the connection evaluating to ``None``
            unless it has been configured by the server.

            If the type is not optional, a default value of ``None`` will result
            in an error, unless the server has set another value in its
            configuration.

            If the type is a mapping of `str` to `.Thing` the default should be
            of type `Sequence[str]` (and could be an empty list).
        """
        super().__init__()
        self._default = default
        self._things: WeakKeyDictionary[
            "Thing", ReferenceType["Thing"] | WeakValueDictionary[str, "Thing"] | None
        ] = WeakKeyDictionary()

    @property
    def thing_type(self) -> tuple[type["Thing"], ...]:
        r"""The `.Thing` subclass(es) returned by this connection.

        A tuple is returned to allow for optional thing conections that
        are typed as the union of two Thing types. It will work with
        `isinstance`\ .
        """
        if not self.is_mapping:
            return self.value_type
        # is_mapping already checks the type is a `Mapping`, so
        # we can just look at its arguments.
        _, thing_type = get_args(self.value_type)
        return thing_type

    @property
    def is_mapping(self) -> bool:
        """Whether we return a mapping of strings to Things, or a single Thing."""
        return get_origin(self.value_type) is Mapping

    @property
    def is_optional(self) -> bool:
        """Whether ``None`` or an empty mapping is an allowed value."""
        if get_origin(self.value_type) in (UnionType, Union):
            if NoneType in get_args(self.value_type):
                return True
        return False

    @property
    def default(self) -> str | Sequence[str] | None:
        """The name of the Thing that will be connected by default, if any."""
        return self._default

    def __set__(self, obj: "Thing", value: ThingSubclass) -> None:
        """Raise an error as this is a read-only descriptor.

        :param obj: the `.Thing` on which the descriptor is defined.
        :param value: the value being assigned.

        :raises AttributeError: this descriptor is not writeable.
        """
        raise AttributeError("This descriptor is read-only.")

    def connect(self, host: "Thing", target: ConnectedThings) -> None:
        r"""Connect a `.Thing` (or several) to a `.ThingConnection`\ .

        This method sets up a ThingConnection on ``host_thing`` such that it will
        supply ``target`` when accessed.

        :param host: the `.Thing` on which the connection is defined.
        :param target: the `.Thing` that will be available as the value
            of the `.ThingConnection` or a sequence of `.Thing` instances,
            or `None`\ .

        :raises ThingConnectionError: if the supplied `.Thing` is of the wrong
            type, if a sequence is supplied when a single `.Thing` is required,
            or if `None` is supplied and the connection is not optional.
        """
        base_msg = f"Can't connect %s to {host.name}.{self.name} "
        thing_type_msg = f"{base_msg} because it is not of type {self.thing_type}."
        unexpected_sequence_msg = f"{base_msg} because a single Thing is needed."
        expected_sequence_msg = f"{base_msg} because a sequence of Things is needed."
        not_optional_msg = f"{base_msg} because it is not optional and has no default."
        if target is None:
            if self.is_optional:
                self._things[host] = None
            else:
                raise ThingConnectionError(not_optional_msg)
        elif isinstance(target, Sequence):
            if self.is_mapping:
                for t in target:
                    if not isinstance(t, self.thing_type):
                        raise ThingConnectionError(thing_type_msg % repr(t))
                self._things[host] = WeakValueDictionary({t.name: t for t in target})
            else:
                raise ThingConnectionError(unexpected_sequence_msg % target)
        else:
            if not self.is_mapping:
                if not isinstance(target, self.thing_type):
                    raise ThingConnectionError(thing_type_msg % repr(target))
                self._things[host] = ref(target)
            else:
                raise ThingConnectionError(expected_sequence_msg % target)

    def instance_get(self, obj: "Thing") -> ConnectedThings:
        r"""Supply the connected `.Thing`\ (s).

        :param obj: The `.Thing` on which the connection is defined.

        :return: the `.Thing` instance(s) connected.

        :raises ThingNotConnectedError: if the ThingConnection has not yet been set up.
        """
        msg = f"{self.name} has not been connected to a Thing yet."
        try:
            val = self._things[obj]
        except KeyError as e:
            raise ThingNotConnectedError(msg) from e
        # Note that ReferenceError is deliberately not handled: the Thing
        # referred to by thing_ref should exist until the server has shut down.
        if isinstance(val, ReferenceType):
            return val()
        else:
            # This works for None or for WeakValueDictionary()
            return val


def thing_connection(default: str | Sequence[str] | None = None) -> Any:
    r"""Declare a connection to another `.Thing` in the same server.

    This function is a convenience wrapper around the `.ThingConnection` descriptor
    class, and should be used in preference to using the descriptor directly.
    The main reason to use the function is that it suppresses type errors when
    using static type checkers such as `mypy` or `pyright`.

    In keeping with `.property` and `.setting`, the type of the attribute should
    be the type of the connected `.Thing`\ . For example:

    .. code-block:: python

        import labthings_fastapi as lt


        class ThingA(lt.Thing): ...


        class ThingB(lt.Thing):
            "A class that relies on ThingA."

            thing_a: ThingA = lt.thing_connection("thing_a")

    In the example above, using `.ThingConnection` directly would assign an object
    with type ``ThingConnection[ThingA]`` to the attribute ``thing_a``, which is
    typed as ``ThingA``\ . This would cause a type error. Using
    `.thing_connection` suppresses this error, as its return type is `Any`\ .

    :param default: The name of the Thing that will be connected by default.
        It is possible to omit this default or set it to ``None``\ , but if that
        is done, it will cause an error unless the connection is explicitly made
        in the server configuration. That is usually not desirable.
    :return: A `.ThingConnection` instance.
    """
    return ThingConnection(default=default)
