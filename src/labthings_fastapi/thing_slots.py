r"""Facilitate connections between Things.

It is often desirable for two Things in the same server to be able to communicate.
In order to do this in a nicely typed way that is easy to test and inspect,
LabThings-FastAPI provides the `.thing_slot`\ . This allows a `.Thing`
to declare that it depends on another `.Thing` being present, and provides a way for
the server to automatically connect the two when the server is set up.

Thing connections are set up **after** all the `.Thing` instances are initialised.
This means you should not rely on them during initialisation: if you attempt to
access a connection before it is provided, it will raise an exception. The
advantage of making connections after initialisation is that circular connections
are not a problem: Thing `a` may depend on Thing `b` and vice versa.

As with properties, thing connections will usually be declared using the function
`.thing_slot` rather than the descriptor directly. This allows them to be
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

        thing_a: ThingA = lt.thing_slot()

        @lt.action
        def say_hello(self) -> str:
            "I'm too lazy to say hello, ThingA does it for me."
            return self.thing_a.say_hello()
"""

from types import EllipsisType, NoneType, UnionType
from typing import Any, Generic, TypeVar, TYPE_CHECKING, Union, get_args, get_origin
from collections.abc import Mapping, Iterable, Sequence
from weakref import ReferenceType, WeakKeyDictionary, ref, WeakValueDictionary
from .base_descriptor import FieldTypedBaseDescriptor
from .exceptions import ThingNotConnectedError, ThingSlotError

if TYPE_CHECKING:
    from .thing import Thing


ThingSubclass = TypeVar("ThingSubclass", bound="Thing")
ConnectedThings = TypeVar(
    "ConnectedThings",
    bound="Mapping[str, Thing] | Thing | None",
)


class ThingSlot(Generic[ConnectedThings], FieldTypedBaseDescriptor[ConnectedThings]):
    r"""Descriptor that instructs the server to supply other Things.

    A `.ThingSlot` provides either one or several
    `.Thing` instances as a property of a `.Thing`\ . This allows `.Thing`\ s
    to communicate with each other within the server, including accessing
    attributes that are not exposed over HTTP.

    While it is possible to dynamically retrieve a `.Thing` from the `.ThingServer`
    this is not recommended: using Thing Connections ensures all the `.Thing`
    instances are available before the server starts, reducing the likelihood
    of run-time crashes.

    The usual way of creating these connections is the function
    `.thing_slot`\ . This class and its subclasses are not usually
    instantiated directly.

    The type of the `.ThingSlot` attribute is key to its operation.
    It should be assigned to an attribute typed either as a `.Thing` subclass,
    a mapping of strings to `.Thing` or subclass instances, or an optional
    `.Thing` instance:

    .. code-block:: python

        class OtherExample(lt.Thing):
            pass


        class Example(lt.Thing):
            # This will always evaluate to an `OtherExample`
            other_thing: OtherExample = lt.thing_slot("other_thing")

            # This may evaluate to an `OtherExample` or `None`
            optional: OtherExample | None = lt.thing_slot("other_thing")

            # This evaluates to a mapping of `str` to `.Thing` instances
            things: Mapping[str, OtherExample] = lt.thing_slot(["thing_a"])
    """

    def __init__(
        self, *, default: str | None | Iterable[str] | EllipsisType = ...
    ) -> None:
        """Declare a ThingSlot.

        :param default: The name of the Thing(s) that will be connected by default.

            If the type is optional (e.g. ``ThingSubclass | None``) a default
            value of ``None`` will result in the connection evaluating to ``None``
            unless it has been configured by the server.

            If the type is not optional, a default value of ``None`` will result
            in an error, unless the server has set another value in its
            configuration.

            If the type is a mapping of `str` to `.Thing` the default should be
            of type `Iterable[str]` (and could be an empty list).
        """
        super().__init__()
        self._default = default
        self._things: WeakKeyDictionary[
            "Thing", ReferenceType["Thing"] | WeakValueDictionary[str, "Thing"] | None
        ] = WeakKeyDictionary()

    @property
    def thing_type(self) -> tuple[type, ...]:
        r"""The `.Thing` subclass(es) returned by this connection.

        A tuple is returned to allow for optional thing connections that
        are typed as the union of two Thing types. It will work with
        `isinstance`\ .
        """
        thing_type = self.value_type
        if self.is_mapping:
            # is_mapping already checks the type is a `Mapping`, so
            # we can just look at its arguments.
            _, thing_type = get_args(self.value_type)
        if get_origin(thing_type) in (UnionType, Union):
            # If it's a Union, we may have an optional type, in which
            # case we want to exclude None.
            return tuple(t for t in get_args(thing_type) if t is not NoneType)
        else:
            # If it's not a Union, it should be a single Thing subclass
            # so wrap it in a tuple.
            return (thing_type,)

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
    def default(self) -> str | Iterable[str] | None | EllipsisType:
        """The name of the Thing that will be connected by default, if any."""
        return self._default

    def __set__(self, obj: "Thing", value: ThingSubclass) -> None:
        """Raise an error as this is a read-only descriptor.

        :param obj: the `.Thing` on which the descriptor is defined.
        :param value: the value being assigned.

        :raises AttributeError: this descriptor is not writeable.
        """
        raise AttributeError("This descriptor is read-only.")

    def _pick_things(
        self,
        things: "Mapping[str, Thing]",
        target: str | Iterable[str] | None | EllipsisType,
    ) -> "Sequence[Thing]":
        r"""Pick the Things we should connect to from a list.

        This function is used internally by `.ThingSlot.connect` to choose
        the Things we return when the `.ThingSlot` is accessed.

        :param things: the available `.Thing` instances on the server.
        :param target: the name(s) we should connect to, or `None` to set the
            connection to `None` (if it is optional). A special value is `...`
            which will pick the `.Thing` instannce(s) matching this connection's
            type hint.

        :raises ThingSlotError: if the supplied `.Thing` is of the wrong
            type, if a sequence is supplied when a single `.Thing` is required,
            or if `None` is supplied and the connection is not optional.
        :raises TypeError: if ``target`` is not one of the allowed types.

        `KeyError` will also be raised if names specified in ``target`` do not
        exist in ``things``\ .

        :return: a list of `.Thing` instances to supply in response to ``__get__``\ .
        """
        if target is None:
            return []
        elif target is ...:
            return [
                thing
                for _, thing in things.items()
                if isinstance(thing, self.thing_type)
            ]
        elif isinstance(target, str):
            if not isinstance(things[target], self.thing_type):
                raise ThingSlotError(f"{target} is the wrong type")
            return [things[target]]
        elif isinstance(target, Iterable):
            for t in target:
                if not isinstance(things[t], self.thing_type):
                    raise ThingSlotError(f"{t} is the wrong type")
            return [things[t] for t in target]
        msg = f"The target specified for a ThingSlot ({target}) has the wrong "
        msg += "type. See ThingSlot.connect() docstring for details."
        raise TypeError(msg)

    def connect(
        self,
        host: "Thing",
        things: "Mapping[str, Thing]",
        target: str | Iterable[str] | None | EllipsisType = ...,
    ) -> None:
        r"""Find the `.Thing`\ (s) we should supply when accessed.

        This method sets up a ThingSlot on ``host_thing`` by finding the
        `.Thing` instance(s) it should supply when its ``__get__`` method is
        called. The logic for determining this is:

        * If ``target`` is specified, we look for the specified `.Thing`\ (s).
          ``None`` means we should return ``None`` - that's only allowed if the
          type hint permits it.
        * If ``target`` is not specified or is ``...`` we use the default value
          set when the connection was defined.
        * If the default value was ``...`` and no target was specified, we will
          attempt to find the `.Thing` by type. Most of the time, this is the
          desired behaviour.

        If the type of this connection is a ``Mapping``\ , ``target`` should be
        a sequence of names. This sequence may be empty.

        ``None`` is treated as equivalent to the empty list, and a list with
        one name in it is treated as equivalent to a single name.

        If the type hint of this connection does not permit ``None``\ , and
        either ``None`` is specified, or no ``target`` is given and the default
        is set as ``None``\ , then an error will be raised. ``None`` will only
        be returned at runtime if it is permitted by the type hint.

        :param host: the `.Thing` on which the connection is defined.
        :param things: the available `.Thing` instances on the server.
        :param target: the name(s) we should connect to, or `None` to set the
            connection to `None` (if it is optional). The default is `...`
            which will use the default that was set when this `.ThingSlot`
            was defined.

        :raises ThingSlotError: if the supplied `.Thing` is of the wrong
            type, if a sequence is supplied when a single `.Thing` is required,
            or if `None` is supplied and the connection is not optional.
        """
        used_target = self.default if target is ... else target
        try:
            # First, explicitly check for None so we can raise a helpful error.
            if used_target is None and not self.is_optional and not self.is_mapping:
                raise ThingSlotError("it must be set in configuration")
            # Most of the logic is split out into `_pick_things` to separate
            # picking the Things from turning them into the correct mapping/reference.
            picked = self._pick_things(things, used_target)
            if self.is_mapping:
                # Mappings may have any number of entries, so no more validation needed.
                self._things[host] = WeakValueDictionary({t.name: t for t in picked})
            elif len(picked) == 0:
                if self.is_optional:
                    # Optional things may be set to None without an error.
                    self._things[host] = None
                else:
                    # Otherwise a single Thing is required, so raise an error.
                    raise ThingSlotError("no matching Thing was found")
            elif len(picked) == 1:
                # A single Thing is found: we can safely use this.
                self._things[host] = ref(picked[0])
            else:
                # If more than one Thing is found (and we're not a mapping) this is
                # an error.
                raise ThingSlotError("it can't connect to multiple Things")
        except (ThingSlotError, KeyError) as e:
            reason = str(e.args[0])
            if isinstance(e, KeyError):
                reason += " is not the name of a Thing"
            msg = f"Can't connect '{host.name}.{self.name}' because {reason}. "
            if target is not ...:
                msg += f"It was configured to connect to '{target}'. "
            else:
                msg += "It was not configured, and used the default. "
            if self.default is not ...:
                msg += f"The default is '{self.default}'."
            else:
                msg += f"The default searches for Things by type: '{self.thing_type}'."

            raise ThingSlotError(msg) from e

    def instance_get(self, obj: "Thing") -> ConnectedThings:
        r"""Supply the connected `.Thing`\ (s).

        :param obj: The `.Thing` on which the connection is defined.

        :return: the `.Thing` instance(s) connected.

        :raises ThingNotConnectedError: if the ThingSlot has not yet been set up.
        :raises ReferenceError: if a connected Thing no longer exists (should not
            ever happen in normal usage).

        Typing notes:

        This must be annotated as ``ConnectedThings`` which is the type variable
        corresponding to the type of this connection. The type determined
        at runtime will be within the upper bound of ``ConnectedThings`` but it
        would be possible for ``ConnectedThings`` to be more specific.

        In general, types determined at runtime may conflict with generic types,
        and at least for this class the important thing is that types determined
        at runtime match the attribute annotations, which is tested in unit tests.

        The return statements here consequently have their types ignored.

        """
        msg = f"{self.name} has not been connected to a Thing yet."
        try:
            val = self._things[obj]
        except KeyError as e:
            raise ThingNotConnectedError(msg) from e
        if isinstance(val, ReferenceType):
            thing = val()
            if thing is not None:
                return thing  # type: ignore[return-value]
                # See docstring for an explanation of the type ignore directives.
            else:
                raise ReferenceError("A connected thing was garbage collected.")
        else:
            # This works for None or for WeakValueDictionary()
            return val  # type: ignore[return-value]
            # See docstring for an explanation of the type ignore directives.


def thing_slot(default: str | Iterable[str] | None | EllipsisType = ...) -> Any:
    r"""Declare a connection to another `.Thing` in the same server.

    ``lt.thing_slot`` marks a class attribute as a connection to another
    `.Thing` on the same server. This will be automatically supplied when the
    server is started, based on the type hint and default value.

    In keeping with `.property` and `.setting`, the type of the attribute should
    be the type of the connected `.Thing`\ . For example:

    .. code-block:: python

        import labthings_fastapi as lt


        class ThingA(lt.Thing): ...


        class ThingB(lt.Thing):
            "A class that relies on ThingA."

            thing_a: ThingA = lt.thing_slot()

    This function is a convenience wrapper around the `.ThingSlot` descriptor
    class, and should be used in preference to using the descriptor directly.
    The main reason to use the function is that it suppresses type errors when
    using static type checkers such as `mypy` or `pyright` (see note below).

    The type hint of a Thing Connection should be one of the following:

    * A `.Thing` subclass. An instance of this subclass will be returned when
        the attribute is accessed.
    * An optional `.Thing` subclass (e.g. ``MyThing | None``). This will either
        return a ``MyThing`` instance or ``None``\ .
    * A mapping of `str` to `.Thing` (e.g. ``Mapping[str, MyThing]``). This will
        return a mapping of `.Thing` names to `.Thing` instances. The mapping
        may be empty.

    Example:

    .. code-block:: python

        import labthings_fastapi as lt


        class ThingA(lt.Thing):
            "An example Thing."


        class ThingB(lt.Thing):
            "An example Thing with connections."

            thing_a: ThingA = lt.thing_slot()
            maybe_thing_a: ThingA | None = lt.thing_slot()
            all_things_a: Mapping[str, ThingA] = lt.thing_slot()

            @lt.thing_action
            def show_connections(self) -> str:
                "Tell someone about our connections."
                self.thing_a  # should always evaluate to a ThingA instance
                self.maybe_thing_a  # will be a ThingA instance or None
                self.all_things_a  # will a mapping of names to ThingA instances
                return f"{self.thing_a=}, {self.maybe_thing_a=}, {self.all_things_a=}"

    The example above is very contrived, but shows how to apply the different types.

    If no default value is supplied, and no value is configured for the connection,
    the server will attempt to find a `.Thing` that
    matches the specified type when the server is started. If no matching `.Thing`
    instances are found, the descriptor will return ``None`` or an empty mapping.
    If that is not allowed by the type hint, the server will fail to start with
    an error.

    The default value may be a string specifying a `.Thing` name, or a sequence of
    strings (for connections that return mappings). In those cases, the relevant
    `.Thing` will be returned from the server. If a name is given that either
    doesn't correspond to a `.Thing` on the server, or is a `.Thing` that doesn't
    match the type of this connection, the server will fail to start with an error.

    The default may also be ``None``
    which is appropriate when the type is optional or a mapping. If the type is
    a `.Thing` subclass, a default value of ``None`` forces the connection to be
    specified in configuration.

    :param default: The name(s) of the Thing(s) that will be connected by default.
        If the default is omitted or set to ``...`` the server will attempt to find
        a matching `.Thing` instance (or instances). A default value of `None` is
        allowed if the connection is type hinted as optional.
    :return: A `.ThingSlot` descriptor.

    Typing notes:

    In the example above, using `.ThingSlot` directly would assign an object
    with type ``ThingSlot[ThingA]`` to the attribute ``thing_a``, which is
    typed as ``ThingA``\ . This would cause a type error. Using
    `.thing_slot` suppresses this error, as its return type is a`Any``\ .

    The use of ``Any`` or an alternative type-checking exemption seems to be
    inevitable when implementing descriptors that are typed via attribute annotations,
    and it is done by established libraries such as `pydantic`\ .

    """
    return ThingSlot(default=default)
