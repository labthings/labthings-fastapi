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
        "The number of times we've incremented the counter."

        target: int = lt.property(default=10)
        "The number of times to increment before we stop."

        @lt.property
        def remaining(self) -> int:
            "The number of steps remaining."
            return self.target - self.count

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
from types import EllipsisType
from typing import (
    Annotated,
    Any,
    Callable,
    Generic,
    TypeAlias,
    TypeVar,
    overload,
    TYPE_CHECKING,
)
from typing_extensions import Self
import typing
from weakref import WeakSet

from fastapi import Body, FastAPI
from pydantic import BaseModel, RootModel

from .thing_description import type_to_dataschema
from .thing_description._model import (
    DataSchema,
    Form,
    PropertyAffordance,
    PropertyOp,
)
from .utilities import labthings_data, wrap_plain_types_in_rootmodel
from .utilities.introspection import return_type
from .base_descriptor import BaseDescriptor
from .exceptions import (
    NotConnectedToServerError,
    ReadOnlyPropertyError,
)

if TYPE_CHECKING:
    from .thing import Thing


# Note on ignored linter codes:
#
# D103 refers to missing docstrings. I have ignored this on @overload definitions
# because they shouldn't have docstrings - the docstring belongs only on the
# function they overload.
# D105 is the same as D103, but for __init__ (i.e. magic methods).
# DOC101 and DOC103 are also a result of overloads not having docstrings
# DOC201 and D401 are ignored on properties. Because we are overriding the
# builtin `property`, we are using `@builtins.property` which is not recognised
# by pydoclint as a property. I've therefore ignored those codes manually.


# The following exceptions are raised only when creating/setting up properties.
class OverspecifiedDefaultError(ValueError):
    """The default value has been specified more than once.

    This error is raised when a `.DataProperty` is instantiated with both a
    ``default`` value and a ``default_factory`` provided.
    """


class MissingDefaultError(ValueError):
    """The default value has not been specified.

    This error is raised when a `.DataProperty` is instantiated without a
    ``default`` value or a ``default_factory`` function.
    """


class InconsistentTypeError(TypeError):
    """Different type hints have been given for a property.

    Every property should have a type hint, which may be provided in a few
    different ways. If multiple type hints are provided, they must match.
    See `.property` for more details.
    """


class MissingTypeError(TypeError):
    """No type hints have been given for a property.

    Every property should have a type hint, which may be provided in a few
    different ways. This error indicates that no type hint was found.
    """


Value = TypeVar("Value")
if TYPE_CHECKING:
    # It's hard to type check methods, because the type of ``self``
    # will be a subclass of `.Thing`, and `Callable` types are
    # contravariant in their arguments (i.e.
    # ``Callable[[SpecificThing,], Value])`` is not a subtype of
    # ``Callable[[Thing,], Value]``.
    # It is probably not particularly important for us to check th
    # type of ``self`` when decorating methods, so it is left as
    # ``Any`` to avoid the major confusion that would result from
    # trying to type it more tightly.
    #
    # Note: in ``@overload`` definitions, it's sometimes necessary
    # to avoid the use of these aliases, as ``mypy`` can't
    # pick which variant is in use without the explicit `Callable`.
    ValueFactory: TypeAlias = Callable[[], Value]
    ValueGetter: TypeAlias = Callable[[Any], Value]
    ValueSetter: TypeAlias = Callable[[Any, Value], None]


def default_factory_from_arguments(
    default: Value | EllipsisType = ...,
    default_factory: ValueFactory | None = None,
) -> ValueFactory:
    """Process default arguments to get a default factory function.

    This function takes the ``default`` and ``default_factory`` arguments
    and will either return the ``default_factory`` if it is provided, or
    will wrap the default value provided in a factory function.

    Note that this wrapping does not copy the default value each time it is
    called, so mutable default values are **only** safe if supplied as a
    factory function.

    This is used to avoid repeating the logic of checking whether a default
    value or a factory function has been provided, and it returns a factory
    rather than a default value so that it may be called multiple times to
    get copies of the default value.

    This function also ensures the default is specified exactly once, and
    raises exceptions if it is not.

    This logic originally lived only in the initialiser of `.DataProperty`
    but it was needed in the `.property` and `.setting` functions in order
    to correctly type them (so that specifying both or neither of the
    ``default`` and ``default_factory`` arguments would raise an error
    with mypy).

    :param default: the default value, or an ellipsis if not specified.
    :param default_factory: a function that returns the default value.
    :return: a function that returns the default value.
    :raises OverspecifiedDefaultError: if both ``default`` and
        ``default_factory`` are specified.
    :raises MissingDefaultError: if neither ``default`` nor ``default_factory``
        are specified.
    """
    if default is ... and default_factory is None:
        # If the default is an ellipsis, we have no default value.
        # Not having a default_factory alongside this
        # is not allowed for DataProperty, so we raise an error.
        raise MissingDefaultError()
    if default is not ... and default_factory is not None:
        # If both default and default_factory are set, we raise an error.
        raise OverspecifiedDefaultError()
    if default is not ...:

        def default_factory() -> Value:
            return default

    if not callable(default_factory):
        raise MissingDefaultError("The default_factory must be callable.")
    return default_factory


# See comment at the top of the file regarding ignored linter rules.
@overload  # use as a decorator  @property
def property(  # noqa: D103
    getter: Callable[[Any], Value],
) -> FunctionalProperty[Value]: ...


@overload  # use as `field: int = property(default=0)`
def property(  # noqa: D103
    *, default: Value, readonly: bool = False
) -> Value: ...


@overload  # use as `field: int = property(default_factory=lambda: 0)`
def property(  # noqa: D103
    *, default_factory: Callable[[], Value], readonly: bool = False
) -> Value: ...


def property(
    getter: ValueGetter | EllipsisType = ...,
    *,
    default: Value | EllipsisType = ...,
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

    :param getter: is a method of a class that returns the value
        of this property. This is usually supplied by using ``property``
        as a decorator.
    :param default: is the default value. Either this, ``getter`` or
        ``default_factory`` must be specified. Specifying both
        or neither will raise an exception.
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

    :raises MissingDefaultError: if no valid default value is supplied,
        and a getter is not in use.
    :raises OverspecifiedDefaultError: if the default is specified more
        than once (e.g. ``default``, ``default_factory``, or ``getter``).

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

    Finally, the type of the ``default`` argument includes `.EllipsisType`
    so that we can use ``...`` as its default value. This allows us to
    distinguish between ``default`` not being set (``...``) and a desired
    default value of ``None``. Similarly, ``...`` is the default value for
    ``getter`` so we can raise a more helpful error if a non-callable
    value is passed as the first argument.
    """
    if getter is not ...:
        # If the default is callable, we're being used as a decorator
        # without arguments.
        if not callable(getter):
            raise MissingDefaultError(
                "A non-callable getter was passed to `property`. Usually,"
                "this means the default value was not passed as a keyword "
                "argument, which is required."
            )
        if default_factory or default is not ...:
            raise OverspecifiedDefaultError(
                "A getter was specified at the same time as a default. Only "
                "one of a getter, default, and default_factory may be used."
            )
        return FunctionalProperty(
            fget=getter,
        )
    return DataProperty(  # type: ignore[return-value]
        default_factory=default_factory_from_arguments(default, default_factory),
        readonly=readonly,
    )


class BaseProperty(BaseDescriptor[Value], Generic[Value]):
    """A descriptor that marks Properties on Things.

    This class is used to determine whether an attribute of a `.Thing` should
    be treated as a Property (see :ref:`wot_properties` - essentially, it
    means the value should be available over HTTP).

    `.BaseProperty` should not be used directly, instead it is recommended to
    use `.property` to declare properties on your `.Thing` subclass.
    """

    def __init__(self) -> None:
        """Initialise a BaseProperty."""
        super().__init__()
        self._type: type | None = None
        self._model: type[BaseModel] | None = None
        self.readonly: bool = False

    @builtins.property
    def value_type(self) -> type[Value]:
        """The type of this descriptor's value.

        :raises MissingTypeError: if the type has not been set.
        :return: the type of the descriptor's value.
        """  # noqa: D401 # see note at the top of the file
        if self._type is None:
            raise MissingTypeError("This property does not have a valid type.")
        return self._type

    @builtins.property
    def model(self) -> type[BaseModel]:
        """A Pydantic model for the property's type.

        `pydantic` models are used to serialise and deserialise values from
        and to JSON. If the property is defined with a type hint that is not
        a `pydantic.BaseModel` subclass, this property will ensure it is
        wrapped in a `pydantic.RootModel` so it can be used with FastAPI.

        If `.BaseProperty.value_type` is already a `pydantic.BaseModel`
        subclass, this returns it unchanged.

        :return: a Pydantic model for the property's type.
        """  # noqa: D401 # see note at the top of the file
        if self._model is None:
            self._model = wrap_plain_types_in_rootmodel(self.value_type)
        return self._model

    def add_to_fastapi(self, app: FastAPI, thing: Thing) -> None:
        """Add this action to a FastAPI app, bound to a particular Thing.

        :param app: The FastAPI application we are adding endpoints to.
        :param thing: The `.Thing` we are adding the endpoints for.
        """
        assert thing.path is not None
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
        assert path is not None, "Cannot create a property affordance without a path"
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


class DataProperty(BaseProperty[Value], Generic[Value]):
    """A Property descriptor that acts like a regular variable.

    `.DataProperty` descriptors remember their value, and can be read and
    written to like a regular Python variable.
    """

    @overload
    def __init__(  # noqa: D105,D107,DOC101,DOC103
        self, default: Value, *, readonly: bool = False
    ) -> None: ...

    @overload
    def __init__(  # noqa: D105,D107,DOC101,DOC103
        self, *, default_factory: ValueFactory, readonly: bool = False
    ) -> None: ...

    def __init__(
        self,
        default: Value | EllipsisType = ...,
        *,
        default_factory: ValueFactory | None = None,
        readonly: bool = False,
    ) -> None:
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
            be provided. Note that, as ``None`` is a valid default value,
            this uses ``...`` instead as a way of checking whether ``default``
            has been set.
        :param default_factory: a function that returns the default value.
            This is appropriate for datatypes such as lists, where using
            a mutable default value can lead to odd behaviour.
        :param readonly: if ``True``, the property may not be written to via
            HTTP, or via `.DirectThingClient` objects, i.e. it may only be
            set as an attribute of the `.Thing` and not from a client.
        """
        super().__init__()
        self._default_factory = default_factory_from_arguments(
            default=default, default_factory=default_factory
        )
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

    @builtins.property
    def value_type(self) -> type[Value]:  # noqa: DOC201
        """The type of the descriptor's value."""  # noqa: D401
        self.assert_set_name_called()
        return super().value_type

    def instance_get(self, obj: Thing) -> Value:
        """Return the property's value.

        This will supply a default if the property has not yet been set.

        :param obj: The `.Thing` on which the property is being accessed.
        :return: the value of the property.
        """
        if self.name not in obj.__dict__:
            # Note that a static default is converted to a factory function
            # in __init__.
            obj.__dict__[self.name] = self._default_factory()
        return obj.__dict__[self.name]

    def __set__(
        self, obj: Thing, value: Value, emit_changed_event: bool = True
    ) -> None:
        """Set the property's value.

        This sets the property's value, and notifies any observers.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value for the property.
        :param emit_changed_event: whether to emit a changed event.
        """
        obj.__dict__[self.name] = value
        if emit_changed_event:
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


class FunctionalProperty(BaseProperty[Value], Generic[Value]):
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
        super().__init__()
        self._fget: ValueGetter = fget
        self._type = return_type(self._fget)
        self._fset: ValueSetter | None = None
        self.readonly: bool = True

    @builtins.property
    def fget(self) -> ValueGetter:  # noqa: DOC201
        """The getter function."""  # noqa: D401
        return self._fget

    @builtins.property
    def fset(self) -> ValueSetter | None:  # noqa: DOC201
        """The setter function."""  # noqa: D401
        return self._fset

    def getter(self, fget: ValueGetter) -> Self:
        """Set the getter function of the property.

        This function returns the descriptor, so it may be used as a decorator.
        If the function has a docstring, it will be used as the property docstring.

        :param fget: The new getter function.
        :return: this descriptor (i.e. ``self``). This allows use as a decorator.
        """
        self._fget = fget
        self._type = return_type(self._fget)
        self.__doc__ = fget.__doc__
        return self

    def setter(self, fset: ValueSetter) -> Self:
        r"""Set the setter function of the property.

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
                def set_myprop(self, val: int) -> None:
                    self._myprop = val

                myprop.readonly = True  # Prevent client code from setting it

        .. note::

            The example code above is not quite what would be done for the built-in
            ``@property`` decorator, because our setter does not have the same name
            as the getter. Using a different name avoids type checkers such as
            ``mypy`` raising an error that the getter has been redefined with a
            different type. The behaviour is identical whether the setter and getter
            have the same name or not. The only difference is that the `.Thing`
            will have an additional method called ``set_myprop`` in the example
            above.

        :param fset: The new setter function.
        :return: this descriptor (i.e. ``self``). This allows use as a decorator.

        **Typing Notes**

        Python's built-in ``property`` is treated as a special case by ``mypy``
        and others, and our descriptor is not treated in the same way.
        Naming the setter and getter the same is required by `builtins.property`
        because the property must be overwritten when the setter is added, as
        `builtins.property` is not mutable.

        Our descriptor is mutable, so the setter may be added without having to
        overwrite the object. While it would be nice to use exactly the same
        conventions as `builtins.property`, it currently causes type errors that
        must be silenced manually. We suggest using a different name for the setter
        as an alternative to adding ``# type: ignore[no-redef]`` to the setter
        function.

        It will cause problems elsewhere in the code if descriptors are assigned
        to more than one attribute, and this is checked in
        `.BaseDescriptor.__set_name__`\ . We therefore return the setter rather
        than the descriptor if the names don't match. The type hint does not
        reflect this, as it would cause problems when the names do match (the
        descriptor would become a ``FunctionalProperty | Callable`` and thus
        typing errors would happen whenever it's accessed).
        """
        self._fset = fset
        self.readonly = False
        if fset.__name__ != self.fget.__name__:
            # Don't return the descriptor if it's named differently.
            # see typing notes in docstring.
            return fset  # type: ignore[return-value]
        return self

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
        if self.fset is None:
            raise ReadOnlyPropertyError(f"Property {self.name} of {obj} has no setter.")
        self.fset(obj, value)


@overload  # use as a decorator  @setting
def setting(  # noqa: D103
    getter: Callable[[Any], Value],
) -> FunctionalSetting[Value]: ...


@overload  # use as `field: int = setting(default=0)``
def setting(  # noqa: D103
    *, default: Value, readonly: bool = False
) -> Value: ...


@overload  # use as `field: int = setting(default_factory=lambda: 0)`
def setting(  # noqa: D103
    *, default_factory: Callable[[], Value], readonly: bool = False
) -> Value: ...


def setting(
    getter: ValueGetter | EllipsisType = ...,
    *,
    default: Value | EllipsisType = ...,
    default_factory: ValueFactory | None = None,
    readonly: bool = False,
) -> FunctionalSetting[Value] | Value:
    r"""Define a Setting on a `.Thing`\ .

    A setting is a property that is saved to disk.

    This function defines a setting, which is a special Property that will
    be saved to disk, so it persists even when the LabThings server is
    restarted. It is otherwise very similar to `.property`\ .

    A type annotation is required, and should follow the same constraints as
    for :deco:`.property`.

    Every ``setting`` on a `.Thing` will be read each time the settings are
    saved, which may be quite frequent. This means your getter must not take
    too long to run, or have side-effects. Settings that use getters and
    setters may be removed in the future pending the outcome of `#159`_.

    .. _`#159`: https://github.com/labthings/labthings-fastapi/issues/159

    If the type is a pydantic BaseModel, then the setter must also be able to accept
    the dictionary representation of this BaseModel as this is what will be used to
    set the Setting when loading from disk on starting the server.

    .. note::
        If a setting is mutated rather than set, this will not trigger saving.
        For example: if a Thing has a setting called ``dictsetting`` holding the
        dictionary ``{"a": 1, "b": 2}`` then ``self.dictsetting = {"a": 2, "b": 2}``
        would trigger saving but ``self.dictsetting[a] = 2`` would not, as the
        setter for ``dictsetting`` is never called.

    :param getter: is a method of a class that returns the value
        of this property. This is usually supplied by using ``property``
        as a decorator.
    :param default: is the default value. Either this, ``getter`` or
        ``default_factory`` must be specified. Specifying both
        or neither will raise an exception.
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

    :raises MissingDefaultError: if no valid default or getter is supplied.
    :raises OverspecifiedDefaultError: if the default is specified more
        than once (e.g. ``default``, ``default_factory``, or ``getter``).

    **Typing Notes**

    See the typing notes on `.property` as they all apply to `.setting` as
    well.
    """
    if getter is not ...:
        # If the default is callable, we're being used as a decorator
        # without arguments.
        if not callable(getter):
            raise MissingDefaultError(
                "A non-callable getter was passed to `setting`. Usually,"
                "this means the default value was not passed as a keyword "
                "argument, which is required."
            )
        if default_factory or default is not ...:
            raise OverspecifiedDefaultError(
                "A getter was specified at the same time as a default. Only "
                "one of a getter, default, and default_factory may be used."
            )
        return FunctionalSetting(
            fget=getter,
        )
    return DataSetting(  # type: ignore[return-value]
        default_factory=default_factory_from_arguments(default, default_factory),
        readonly=readonly,
    )


class BaseSetting(BaseProperty[Value], Generic[Value]):
    r"""A base class for settings.

    This is a subclass of `.BaseProperty` that is used to define settings.
    It is not intended to be used directly, but via `.setting` and the
    two concrete implementations: `.DataSetting` and `.FunctionalSetting`\ .
    """

    def set_without_emit(self, obj: Thing, value: Value) -> None:
        """Set the setting's value without emitting an event.

        This is used to set the setting's value without notifying observers.
        It is used during initialisation to set the value from disk before
        the server is fully started.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.

        :raises NotImplementedError: this method should be implemented in subclasses.
        """
        raise NotImplementedError("This method should be implemented in subclasses.")


class DataSetting(DataProperty[Value], BaseSetting[Value], Generic[Value]):
    """A `.DataProperty` that persists on disk.

    A setting can be accessed via the HTTP API and is persistent between sessions.

    A `.DataSetting` is a `.DataProperty` with extra functionality for triggering
    a `.Thing` to save its settings.

    Note: If a setting is mutated rather than assigned to, this will not trigger saving.
    For example: if a Thing has a setting called `dictsetting` holding the dictionary
    `{"a": 1, "b": 2}` then `self.dictsetting = {"a": 2, "b": 2}` would trigger saving
    but `self.dictsetting[a] = 2` would not, as the setter for `dictsetting` is never
    called.

    The setting otherwise acts just like a normal variable.
    """

    def __set__(
        self, obj: Thing, value: Value, emit_changed_event: bool = True
    ) -> None:
        """Set the setting's value.

        This will cause the settings to be saved to disk.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        :param emit_changed_event: whether to emit a changed event.
        """
        super().__set__(obj, value, emit_changed_event)
        obj.save_settings()

    def set_without_emit(self, obj: Thing, value: Value) -> None:
        """Set the property's value, but do not emit event to notify the server.

        This function is not expected to be used externally. It is called during
        initial setup so that the setting can be set from disk before the server
        is fully started.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        """
        super().__set__(obj, value, emit_changed_event=False)


class FunctionalSetting(FunctionalProperty[Value], BaseSetting[Value], Generic[Value]):
    """A `.FunctionalProperty` that persists on disk.

    A setting can be accessed via the HTTP API and is persistent between sessions.

    A `.FunctionalSetting` is a `.FunctionalProperty` with extra functionality for
    triggering a `.Thing` to save its settings.

    Note: If a setting is mutated rather than assigned to, this will not trigger
    saving. For example: if a Thing has a setting called ``dictsetting`` holding
    the dictionary ``{"a": 1, "b": 2}`` then ``self.dictsetting = {"a": 2, "b": 2}``
    would trigger saving but ``self.dictsetting[a] = 2`` would not, as the setter
    for ``dictsetting`` is never called.

    The setting otherwise acts just like a `.FunctionalProperty``, i.e. it uses a
    getter and a setter function.
    """

    def __set__(self, obj: Thing, value: Value) -> None:
        """Set the setting's value.

        This will cause the settings to be saved to disk.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        """
        super().__set__(obj, value)
        obj.save_settings()

    def set_without_emit(self, obj: Thing, value: Value) -> None:
        """Set the property's value, but do not emit event to notify the server.

        This function is not expected to be used externally. It is called during
        initial setup so that the setting can be set from disk before the server
        is fully started.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        """
        # FunctionalProperty does not emit changed events, so no special
        # behaviour is needed.
        super().__set__(obj, value)
