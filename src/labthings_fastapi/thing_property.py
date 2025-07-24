"""Define properties of `.Thing` objects.

:ref:`wot_properties` are attributes of a `.Thing` that may be read or written to
over HTTP, and they are described in :ref:`gen_docs`. They are implemented with
a function `.property` (usually referenced as ``lt.property``), which is
intentionally similar to Python's built in `property`.

Properties can be defined in two ways as shown below:

.. code-block:: python

    import labthings_fastapi as lt

    class Counter(lt.Thing):
        "A counter that knows what's remaining."

        count: int = lt.property(default=0, readonly=True)
        "The number of times we've increnented the counter."

        target: int = lt.property(default=10)
        "The number of times to increment before we stop."

        @lt.property
        def remaining(self) -> int:
            "The number of steps remaining."
            return self.remaining - self.count

        @remaining.setter
        def remaining(self, value: int) -> None:
            self.target = self.count + value

    The first two properties are simple variables: they may be read and assigned
    to, and will behave just like a regular variable. Their syntax is similar to
    `dataclasses` or `pydantic` in that `.property` is used as a "field specifier"
    to set options like the default value, and the type annotation is on the
    class attribute. Documentation is in strings immediately following the
    properties, which is understood by most automatic documentation tools.

    ``remaining`` is defined using a "getter" function, meaning this code will
    be run each time ``counter.remaining`` is accessed. Its type will be the
    return type of the function, and its docstring will come from the function
    too. Setters with only a getter are read-only.

    Adding a "setter" to properties is optional, and makes them read-write.
"""

from __future__ import annotations
import builtins
from typing import (
    Annotated,
    Callable,
    Generic,
    Self,
    TypeVar,
    overload,
    TYPE_CHECKING,
)
import typing
from weakref import WeakSet

from fastapi import Body, FastAPI
from pydantic import RootModel

from labthings_fastapi.thing_description import type_to_dataschema
from labthings_fastapi.thing_description._model import (
    DataSchema,
    Form,
    PropertyAffordance,
    PropertyOp,
)
from labthings_fastapi.utilities import labthings_data

from .utilities.introspection import return_type
from .base_descriptor import BaseDescriptor
from .exceptions import (
    DocstringToMessage,
    NotConnectedToServerError,
    ReadOnlyPropertyError,
)

if TYPE_CHECKING:
    from .thing import Thing


# The following exceptions are raised only when creating/setting up properties.
class OverspecifiedDefaultError(DocstringToMessage, ValueError):
    """The default value has been specified more than once.

    This error is raised when a `.DataProperty` is instantiated with both a
    ``default`` value and a ``default_factory`` provided.
    """


class MissingDefaultError(DocstringToMessage, ValueError):
    """The default value has not been specified.

    This error is raised when a `.DataProperty` is instantiated without a
    ``default`` value or a ``default_factory`` function.
    """


class InconsistentTypeError(DocstringToMessage, TypeError):
    """Different type hints have been given for a property.

    Every property should have a type hint, which may be provided in a few
    different ways. If multiple type hints are provided, they must match.
    See `.property` for more details.
    """


class MissingTypeError(DocstringToMessage, TypeError):
    """No type hints have been given for a property.

    Every property should have a type hint, which may be provided in a few
    different ways. This error indicates that no type hint was found.
    """


# fmt: off
Value = TypeVar("Value")
if TYPE_CHECKING:
    ValueFactory = Callable[[None,], Value]
    ValueGetter = Callable[[Thing,], Value]
    ValueSetter = Callable[[Thing, Value], None]
# fmt: on


# D103 ignores missing docstrings on overloads. This shouldn't be raised on overloads.
@overload  # use as a decorator  @property
def property(default: ValueGetter) -> FunctionalProperty[Value]: ...  # noqa: D103
@overload  # use as `field: int = property(0)``
def property(default: Value, *, readonly: bool = False) -> Value: ...  # noqa: D103
@overload  # use as `field: int = property(default_factory=lambda: 0)`
def property(default_factory: ValueFactory, readonly: bool = False) -> Value: ...  # noqa: D103


def property(
    default: Value | ValueGetter | None = None,
    *,
    default_factory: ValueFactory | None = None,
    readonly: bool = False,
) -> Value | FunctionalProperty[Value]:
    r"""Define a Property on a `.Thing`\ .

    This function may be used to define :ref:`wot_properties` in
    two ways, as either a decorator or a field specifier. See the
    examples in the :mod:`.thing_property` documentation.

    Properties should always have a type annotation. This type annotation
    will be used in automatic documentation and also to serialise the value
    to JSON when it is sent over the network. This mean that the type of your
    property should either be JSON serialisable (i.e. simple built-in types)
    or a subclass of `pydantic.BaseModel`.

    :param default: is the default value. Either this or
        ``default_factory`` must be specified.

        When ``property`` is used as a decorator, the function
        being decorated is passed as the first argument, which is
        why this argument also accepts callable objects. Callable
        default values are not supported. If you want to set your
        default value with a function, see ``default_factory``.
    :param default_factory: should return your default value.
        This may be used as an alternative to ``default`` if you
        need to use a mutable datatype. For example, it would be
        better to specify ``default_factory=list`` than
        ``default=[]`` because the second form would be shared
        between all `.Thing`\ s with this property.
    :param readonly: whether the property should be read-only
        via the `.ThingClient` interface (i.e. over HTTP or via
        a `.DirectThingClient`). This is automatically true if
        ``property`` is used as a decorator and no setter is
        specified.

    :return: a property descriptor, either a `.FunctionalProperty`
        if used as a decorator, or a `.DataProperty` if used as
        a field.

    **Typing Notes**

    This function has somewhat complicated type hints, for two reasons.
    Firstly, it may be used either as a decorator or as a field specifier,
    so ``default`` performs double duty as a default value or a getter.
    Secondly, when used as a field specifier the type hint for the
    property is attached to the attribute of the class to which the
    function's output is assigned. This means ``property`` does not know
    its type hint until after it's been called.

    When used as a field specifier, ``property`` returns a generic
    `.DataProperty` descriptor instance, which will determine its type
    when it is attached to the `.Thing`. The type hint on the return
    value of ``property`` in that situation is a "white lie": we annotate
    the return as having the same type as the ``default`` value (or the
    ``default_factory`` return value). This means that type checkers such
    as ``mypy`` will check that the default is valid for the type of the
    field, and won't raise an error about assigning, for example, an
    instance of ``DataProperty[int]`` to a field annotated as ``int``.
    """
    if callable(default):
        # If the default is callable, we're being used as a decorator
        # without arguments.
        func = default
        return FunctionalProperty[return_type(func)](
            fget=func,
        )
    return DataProperty(  # type: ignore[return-value]
        default=default,
        default_factory=default_factory,
        readonly=readonly,
    )


class BaseProperty(BaseDescriptor[Value], Generic[Value]):
    """A descriptor that marks Properties on Things.

    This class is used to determine whether an attribute of a `.Thing` should
    be treated as a Property (see :ref:`wot_properties` - essentially, it
    means the value should be available over HTTP).

    `.BaseProperty` should not be used directly, instead it is recommended to
    use `.property` to declare properties on you `.Thing` subclass.
    """


class DataProperty(BaseProperty[Value], Generic[Value]):
    """A Property descriptor that acts like a regular variable.

    `.DataProperty` descriptors remember their value, and can be read and
    written to like a regular Python variable.
    """

    def __init__(
        self,
        default: Value | None = None,
        *,
        default_factory: ValueFactory | None,
        readonly: bool = False,
    ):
        """Create a property that acts like a regular variable.

        `.DataProperty` descriptors function just like variables, in that
        they can be read and written to as attributes of the `.Thing` and
        their value will be the same every time it is read (i.e. it changes
        only when it is set). This differs from `.FunctionalProperty` which
        uses a "getter" function just like `builtins.property` and may
        return a different value each time.

        `.DataProperty` instances may always be set, when they are accessed
        as an attribute of the `.Thing` instance. The ``readonly`` parameter
        applies only to client code, whether it is remote or a
        `.DirectThingClient` wrapper.

        The type of the property's value will be inferred either from the
        type subscript or from an annotation on the class attribute. This
        is done in ``__get_name__`` because neither is available during
        ``__init__``.

        :param default: the default value. This or ``default_factory`` must
            be provided.
        :param default_factory: a function that returns the default value.
            This is appropriate for datatypes such as lists, where using
            a mutable default value can lead to odd behaviour.
        :param readonly: if ``True``, the property may not be written to via
            HTTP, or via `.DirectThingClient` objects, i.e. it may only be
            set as an attribute of the `.Thing` and not from a client.

        :raises OverspecifiedDefaultError: if both a default and a default
            factory function are specified.
        :raises MissingDefaultError: if no default is provided.
        """
        if default_factory is not None:
            if default is not None:
                raise OverspecifiedDefaultError()
            self._default_value: Value = default_factory()
        if default is None:
            raise MissingDefaultError()
        self._default_value: Value = default
        self.readonly = readonly
        self._type: type | None = None  # Will be set in __set_name__

    def __set_name__(self, owner: type[Thing], name: str) -> None:
        """Take note of the name and type.

        This function is where we determine the type of the property. It may
        be specified in two ways: either by subscripting ``DataProperty``
        or by annotating the attribute:

        .. code-block:: python

            class MyThing(Thing):
                subscripted_property = DataProperty[int](0)
                annotated_property: int = DataProperty(0)

        The second form often works better with autocompletion, though it is
        preferred to use `.property` for consistent naming.

        Neither form allows us to access the type during ``__init__``, which
        is why we find the type here. If there is a problem, exceptions raised
        will appear to come from the class definition, so it's important to
        include the name of the attribute.

        See :ref:`descriptors` for links to the Python docs about when
        this function is called.

        :param owner: the `.Thing` subclass to which we are being attached.
        :param name: the name to which we have been assigned.

        :raises InconsistentTypeError: if the type is specified twice and
            the two types are not identical.
        :raises MissingTypeError: if no type hints have been given.
        """
        # Call BaseDescriptor so we remember the name
        super().__set_name__(owner, name)

        # Check for type subscripts
        if hasattr(self, "__orig_class__"):
            # We have been instantiated with a subscript, e.g. BaseProperty[int].
            #
            # __orig_class__ is set on generic classes when they are instantiated
            # with a subscripted type.
            self._type = typing.get_args(self.__orig_class__)[0]

        # Check for annotations on the parent class
        annotations = typing.get_type_hints(owner, include_extras=True)
        field_annotation = annotations.get(name, None)
        if field_annotation is not None:
            # We have been assigned to an annotated class attribute, e.g.
            # myprop: int = BaseProperty(0)
            if self._type is not None and self._type != field_annotation:
                raise InconsistentTypeError(
                    f"Property {name} on {owner} has conflicting types.\n\n"
                    f"The field annotation of {field_annotation} conflicts "
                    f"with the inferred type of {self._type}."
                )
            self._type = field_annotation
        if self._type is None:
            raise MissingTypeError(
                f"No type hint was found for property {name} on {owner}."
            )

    def instance_get(self, obj: Thing) -> Value:
        """Return the property's value.

        This will supply a default if the property has not yet been set.

        :param obj: The `.Thing` on which the property is being accessed.
        :return: the value of the property.
        """
        try:
            return obj.__dict__[self.name]
        except KeyError:
            return self._default_value

    def __set__(self, obj: Thing, value: Value) -> None:
        """Set the property's value.

        This sets the property's value, and notifies any observers.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value for the property.
        """
        obj.__dict__[self.name] = value
        self.emit_changed_event(obj, value)

    def _observers_set(self, obj: Thing):
        """Return the observers of this property.

        Each observer in this set will be notified when the property is changed.
        See ``.DataProperty.emit_changed_event``

        :param obj: the `.Thing` to which we are attached.

        :return: the set of observers corresponding to ``obj``.
        """
        ld = labthings_data(obj)
        if self.name not in ld.property_observers:
            ld.property_observers[self.name] = WeakSet()
        return ld.property_observers[self.name]

    def emit_changed_event(self, obj: Thing, value: Value) -> None:
        """Notify subscribers that the property has changed.

        This function is run when properties are updated. It must be run from
        within a thread. This could be the `Invocation` thread of a running action, or
        the property should be updated over via a client/http. It must be run from a
        thread as it is communicating with the event loop via an `asyncio` blocking
        portal and can cause deadlock if run in the event loop.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new property value, to be sent to observers.

        :raise NotConnectedToServerError: if the Thing that is calling the property
            update is not connected to a server with a running event loop.
        """
        runner = obj._labthings_blocking_portal
        if not runner:
            thing_name = obj.__class__.__name__
            msg = (
                f"Cannot emit property updated changed event. Is {thing_name} "
                "connected to a running server?"
            )
            raise NotConnectedToServerError(msg)
        runner.start_task_soon(
            self.emit_changed_event_async,
            obj,
            value,
        )

    async def emit_changed_event_async(self, obj: Thing, value: Value):
        """Notify subscribers that the property has changed.

        This function may only be run in the `anyio` event loop. See
        `.DataProperty.emit_changed_event`.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new property value, to be sent to observers.
        """
        for observer in self._observers_set(obj):
            await observer.send(
                {"messageType": "propertyStatus", "data": {self._name: value}}
            )

    def add_to_fastapi(self, app: FastAPI, thing: Thing) -> None:
        """Add this action to a FastAPI app, bound to a particular Thing.

        :param app: The FastAPI application we are adding endpoints to.
        :param thing: The `.Thing` we are adding the endpoints for.
        """
        # We can't use the decorator in the usual way, because we'd need to
        # annotate the type of `body` with `self.model` which is only defined
        # at runtime.
        # The solution below is to manually add the annotation, before passing
        # the function to the decorator.
        if not self.readonly:

            def set_property(body):  # We'll annotate body later
                if isinstance(body, RootModel):
                    body = body.root
                return self.__set__(thing, body)

            set_property.__annotations__["body"] = Annotated[self.model, Body()]
            app.put(
                thing.path + self.name,
                status_code=201,
                response_description="Property set successfully",
                summary=f"Set {self.title}",
                description=f"## {self.title}\n\n{self.description or ''}",
            )(set_property)

        @app.get(
            thing.path + self.name,
            response_model=self.model,
            response_description=f"Value of {self.name}",
            summary=self.title,
            description=f"## {self.title}\n\n{self.description or ''}",
        )
        def get_property():
            return self.__get__(thing)

    def property_affordance(
        self, thing: Thing, path: str | None = None
    ) -> PropertyAffordance:
        """Represent the property in a Thing Description.

        :param thing: the `.Thing` to which we are attached.
        :param path: the URL of the `.Thing`. If not present, we will retrieve
            the ``path`` from ``thing``.

        :return: A description of the property in :ref:`wot_td` format.
        """
        path = path or thing.path
        ops = [PropertyOp.readproperty]
        if not self.readonly:
            ops.append(PropertyOp.writeproperty)
        forms = [
            Form[PropertyOp](
                href=path + self.name,
                op=ops,
            ),
        ]
        data_schema: DataSchema = type_to_dataschema(self.model)
        pa: PropertyAffordance = PropertyAffordance(
            title=self.title,
            forms=forms,
            description=self.description,
        )
        # We merge the data schema with the property affordance (which subclasses the
        # DataSchema model) with the affordance second so its values take priority.
        # Note that this works because all of the fields that get filled in by
        # DataSchema are optional - so the PropertyAffordance is still valid without
        # them.
        return PropertyAffordance(
            **{
                **data_schema.model_dump(exclude_none=True),
                **pa.model_dump(exclude_none=True),
            }
        )


def setting(
    default: Value | None = None,
    *,
    default_factory: ValueFactory | None = None,
    readonly: bool = False,
) -> ThingSetting[Value]:
    r"""Define a Setting on a `.Thing`\ .

    A setting is a property that is saved to disk

    This function defines a setting, which is a special Property that will
    be saved to disk, so it persists even when the LabThings server is
    restarted. It is otherwise very similar to `.property` with the exception
    that it may only be used as a field, i.e. not as a decorator. Settings may not
    be implemented with getter and setter methods, as this can conflict
    with loading and saving to disk.

    A type annotation is required, and should follow the same constraints as
    for :deco:`.property`.

    If the type is a pydantic BaseModel, then the setter must also be able to accept
    the dictionary representation of this BaseModel as this is what will be used to
    set the Setting when loading from disk on starting the server.

    .. note::
        If a setting is mutated rather than set, this will not trigger saving.
        For example: if a Thing has a setting called ``dictsetting`` holding the
        dictionary ``{"a": 1, "b": 2}`` then ``self.dictsetting = {"a": 2, "b": 2}``
        would trigger saving but ``self.dictsetting[a] = 2`` would not, as the
        setter for ``dictsetting`` is never called.

    :param default: is the default value. Either this or
        ``default_factory`` must be specified.
    :param default_factory: should return your default value.
        This may be used as an alternative to ``default`` if you
        need to use a mutable datatype. For example, it would be
        better to specify ``default_factory=list`` than
        ``default=[]`` because the second form would be shared
        between all `.Thing`\ s with this setting.
    :param readonly: whether the setting should be read-only
        via the `.ThingClient` interface (i.e. over HTTP or via
        a `.DirectThingClient`).

    :return: a setting descriptor.

    **Typing Notes**

    The return type of this function is a "white lie" in order to allow
    dataclass-style type annotations
    """
    return ThingSetting(
        default=default,
        default_factory=default_factory,
        readonly=readonly,
    )


class ThingSetting(DataProperty[Value], Generic[Value]):
    """A `.DataProperty` that persists on disk.

    A setting can be accessed via the HTTP API and is persistent between sessions.

    A `.ThingSetting` is a `.DataProperty` with extra functionality for triggering
    a `.Thing` to save its settings.

    Note: If a setting is mutated rather than assigned to, this will not trigger saving.
    For example: if a Thing has a setting called `dictsetting` holding the dictionary
    `{"a": 1, "b": 2}` then `self.dictsetting = {"a": 2, "b": 2}` would trigger saving
    but `self.dictsetting[a] = 2` would not, as the setter for `dictsetting` is never
    called.

    The setting otherwise acts just like a normal variable.
    """

    def __set__(self, obj: Thing, value: Value):
        """Set the setting's value.

        This will cause the settings to be saved to disk.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        """
        super().__set__(obj, value)
        obj.save_settings()

    def set_without_emit(self, obj: Thing, value: Value):
        """Set the property's value, but do not emit event to notify the server.

        This function is not expected to be used externally. It is called during
        initial setup so that the setting can be set from disk before the server
        is fully started.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        """
        obj.__dict__[self.name] = value
        if self._setter:
            self._setter(obj, value)


class FunctionalProperty(BaseProperty[Value], Generic[Value], builtins.property):
    """A property that uses a getter and a setter.

    For properties that should work like variables, use `.DataProperty`. For
    properties that need to run code every time they are read, use this class.

    Functional properties should work very much like Python's `builtins.property`
    except that they are also available over HTTP.
    """

    def __init__(
        self,
        fget: ValueGetter,
    ):
        """Set up a FunctionalProperty.

        Create a descriptor for a property that uses a getter function.

        This class also inherits from `builtins.property` to help type checking
        tools understand that it functions like a property.

        :param fget: the getter function, called when the property is read.
        """
        self._fget: ValueGetter = fget
        self._fset: ValueSetter | None = None
        self.readonly: bool = True

    # Note: DOC201 and DOC401 are ignored on these properties, as
    # they only apply to functions. Pydoclint doesn't recognise these
    # as properties, because we use `builtins.property` and not `property`.
    @builtins.property
    def fget(self) -> ValueGetter:  # noqa: DOC201
        """The getter function."""  # noqa: D401
        return self._fget

    @builtins.property
    def fset(self) -> ValueSetter | None:  # noqa: DOC201
        """The setter function."""  # noqa: D401
        return self._fset

    @builtins.property
    def fdel(self) -> None:  # noqa: DOC201
        """The deleter function.

        This function always returns ``None`` as deleters are not yet supported.
        """  # noqa: D401
        return None

    def getter(self, fget: ValueGetter) -> Self:
        """Set the getter function of the property.

        This function returns the descriptor, so it may be used as a decorator.
        If the function has a docstring, it will be used as the property docstring.

        :param fget: The new getter function.
        :return: this descriptor (i.e. ``self``). This allows use as a decorator.
        """
        self._fget = fget
        if fget.__doc__:
            self.__doc__ = fget.__doc__

    def setter(self, fset: ValueSetter) -> Self:
        """Set the setter function of the property.

        This function returns the descriptor, so it may be used as a decorator.

        Once a setter has been added to a property, it will automatically become
        writeable from client code (over HTTP and via `.DirectThingClient`).
        To override this behaviour you may set ``readonly`` back to ``True``.

        .. code-block:: python

            class MyThing(lt.Thing):
                def __init__(self):
                    self._myprop: int = 0

                @lt.property
                def myprop(self) -> int:
                    "An example property that is an integer"
                    return self._myprop

                @myprop.setter
                def myprop(self, val: int):
                    self._myprop = val

                myprop.readonly = True  # Prevent client code from setting it

        :param fset: The new setter function.
        :return: this descriptor (i.e. ``self``). This allows use as a decorator.
        """
        self._fset = fset
        self.readonly = False

    def deleter(self, fdel: callable) -> Self:
        """Set a deleter function. Currently unsupported.

        :param fdel: The function called when the attribute is deleted.
        :return: The descriptor (i.e. ``self``).

        :raises NotImplementedError: every time, because it is not supported.
        """
        raise NotImplementedError(
            "Deleter functions are not supported for FunctionalProperty."
        )

    def instance_get(self, obj: Thing) -> Value:
        """Get the value of the property.

        :param obj: the `.Thing` on which the attribute is accessed.
        :return: the value of the property.
        """
        return self.fget(obj)

    def __set__(self, obj: Thing, value: Value):
        """Set the value of the property.

        :param obj: the `.Thing` on which the attribute is accessed.
        :param value: the value of the property.

        :raises ReadOnlyPropertyError: if the property cannot be set.
        """
        if self.fset:
            self.fset(obj, value)
        raise ReadOnlyPropertyError(f"Property {self.name} of {obj} has no setter.")
