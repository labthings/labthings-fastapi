"""
Define an object to represent an Action, as a descriptor.
"""

from __future__ import annotations
from types import EllipsisType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Optional,
    Generic,
    Type,
    TypeAlias,
    TypeVar,
    overload,
)
import typing
from weakref import WeakSet

from typing_extensions import Self
from pydantic import BaseModel, RootModel
from fastapi import Body, FastAPI

from ..utilities import labthings_data, wrap_plain_types_in_rootmodel
from ..utilities.introspection import get_summary, get_docstring
from ..thing_description.model import PropertyAffordance, Form, DataSchema, PropertyOp
from ..thing_description import type_to_dataschema
from ..exceptions import NotConnectedToServerError


if TYPE_CHECKING:
    from ..thing import Thing


class MissingTypeError(TypeError):
    """Error raised when a type annotation is missing for a property."""


class MismatchedTypeError(TypeError):
    """Error raised when a type annotation does not match the expected type for a property."""


class MissingDefaultError(AttributeError):
    """Error raised when a property has no getter or initial value."""


Value = TypeVar("Value")
Owner: TypeAlias = "Thing"
# There was an intention to make ThingProperty generic in 2 variables, one for
# the value and one for the owner, but this was problematic.
# For now, we'll stick to typing the owner as a Thing.
# We may want to search-and-replace the Owner symbol, but I think it is
# helpful for now. I don't think NewType would be appropriate here,
# as it would probably raise errors when defining getter/setter methods.


class ThingProperty(Generic[Value]):
    """A property that can be accessed via the HTTP API

    By default, a ThingProperty is "dumb", i.e. it acts just like
    a normal variable. It can have a getter and setter, in which case
    it will work similarly to a Python property.
    """

    model: type[BaseModel]
    """A Pydantic model that describes the type of the property."""
    readonly: bool = False
    """If True, the property cannot be set via the HTTP API"""
    _model_arg: type[Value]
    """The type of the model argument, if specified."""
    _value_type: type[Value]
    """The type of the value, may or may not be a Pydantic model."""

    def __init__(
        self,
        model: type | None = None,
        initial_value: Value | EllipsisType = ...,
        readonly: bool = False,
        observable: bool = False,
        description: Optional[str] = None,
        title: Optional[str] = None,
        getter: Optional[
            Callable[
                [
                    Owner,
                ],
                Value,
            ]
        ] = None,
        setter: Optional[Callable[[Owner, Value], None]] = None,
    ):
        """A property that can be accessed via the HTTP API

        ThingProperty is a descriptor that functions like a variable, optionally
        with notifications when it is set. It may also have a getter and setter,
        which work in a similar way to Python properties.

        The type of a property can be set in several ways:
        1. As a type argument on the property itself, e.g. `ThingProperty[int]`
        2. As a type annotation on the class, e.g. `my_property: int = ThingProperty`
        3. As a type annotation on the getter method, e.g.
           `@ThingProperty\n def my_property(self) -> int: ...`
        4. As an explicitly set model argument, e.g. `ThingProperty(model=int)`

        All of these are checked, and an error is raised if any of them are inconsistent.
        If no type is specified, an error is raised. `model` may be deprecated in the
        future.

        ``ThingProperty`` can behave in several different ways:
        - If no `getter` or `setter` is specified, it will behave like a simple
            data attribute (i.e. a variable). If `observable` is `True`, it is
            possible to register for notifications when the value is set. In this
            case, an `initial_value` is required.
        - If a `getter` is specified and `observable` is `False`, the `getter`
            will be called when the property is accessed, and its return value
            will be the property's value, just like the builtin `property`. The
            property will be read-only both locally and via HTTP.
        - If a `getter` is specified and `observable` is `True`, the `getter`
            is used instead of `initial_value` but thereafter the property
            behaves like a variable. The `getter` is only on first access.
            The property may be written to locally, and whether it's writable
            via HTTP depends on the `readonly` argument.
        - If both a `getter` and `setter` are specified and `observable` is `False`,
            the property behaves like a Python property, with the `getter` being
            called when the property is accessed, and the `setter` being called
            when the property is set. The property is read-only via HTTP if
            `readonly` is `True`. It may always be written to locally.
        - If `observable` is `True` and a `setter` is specified, the property
            will behave like a variable, but will call the `setter`
            when the property is set. The `setter` may perform tasks like sending
            the updated value to the hardware, but it is not responsible for
            remembering the value. The initial value is set via the `getter` or
            `initial_value`.


        :param model: The type of the property. This is optional, because it is
            better to use type hints (see notes on typing above).
        :param initial_value: The initial value of the property. If this is set,
            the property must not have a getter, and should behave like a variable.
        :param readonly: If True, the property cannot be set via the HTTP API.
        :param observable: If True, the property can be observed for changes.
        :param description: A description of the property, used in the API documentation.
            LabThings will attempt to take this from the docstring if not supplied.
        :param title: A human-readable title for the property, used in the API
            documentation. Defaults to the first line of the docstring, or the name
            of the property.
        :param getter: A function that gets the value of the property.
        :param setter: A function that sets the value of the property.
        """
        if getter and not isinstance(initial_value, EllipsisType):
            raise ValueError("getter and an initial value are mutually exclusive.")
        if isinstance(initial_value, EllipsisType) and getter is None:
            raise MissingDefaultError()
        # We no longer check types in __init__, as we do that in __set_name__
        if isinstance(model, type):
            self._model_arg = model
        self.readonly = readonly
        self.observable = observable
        self.initial_value = initial_value
        self._description = description
        self._title = title
        # The lines below allow _getter and _setter to be specified by subclasses
        self._setter = setter or getattr(self, "_setter", None)
        self._getter = getter or getattr(self, "_getter", None)
        # Try to generate a DataSchema, so that we can raise an error that's easy to
        # link to the offending ThingProperty

    def __set_name__(self, owner: type[Owner], name: str) -> None:
        """Notification of the name and owning class.

        When a descriptor is attached to a class, Python calls this method.
        We use it to take note of the property's name and the class it belongs to,
        which also allows us to check if there is a type annotation for the property
        on the class.

        The type of a property can be set in several ways:
        1. As a type argument on the property itself, e.g. `BaseThingProperty[int]`
        2. As a type annotation on the class, e.g. `my_property: int = BaseThingProperty`
        3. As a type annotation on the getter method, e.g. `@BaseThingProperty\n def my_property(self) -> int: ...`

        There is a model argument, e.g. `BaseThingProperty(model=int)` but this is no longer
        supported and will raise an error.

        All of these are checked, and an error is raised if any of them are inconsistent.
        If no type is specified, an error is raised.

        This method is called after `__init__`, so if there was a type subscript
        (e.g. `BaseThingProperty[ModelType]`), it will be available as
        `self.__orig_class__` at this point (but not during `__init__`).

        :param owner: The class that owns this property.
        :param name: The name of the property.

        :raises MissingTypeError: If no type annotation is found for the property.
        :raises MismatchedTypeError: If multiple type annotations are found and they do not agree.
        """
        self._name = name
        value_types: dict[str, type[Value]] = {}
        if hasattr(self, "_model_arg"):
            # If we have a model argument, we can use that
            value_types["model_argument"] = self._model_arg
        if self._getter is not None:
            # If the property has a getter, we can extract the type from it
            annotations = typing.get_type_hints(self._getter, include_extras=True)
            if "return" in annotations:
                value_types["getter_return_type"] = annotations["return"]
        owner_annotations = typing.get_type_hints(owner, include_extras=True)
        if name in owner_annotations:
            # If the property has a type annotation on the owning class, we can use that
            value_types["class_annotation"] = owner_annotations[name]
        if hasattr(self, "__orig_class__"):
            # We were instantiated as BaseThingProperty[ModelType] so can use that type
            value_types["__orig_class__"] = typing.get_args(self.__orig_class__)[0]

        # Check we have a model, and that it is consistent if it's specified in multiple places
        try:
            # Pick the first one we find, then check the rest against it
            self._value_type = next(iter(value_types.values()))
            for v_type in value_types.values():
                if v_type != self._value_type:
                    raise MismatchedTypeError(
                        f"Inconsistent model for property '{name}' on '{owner}'. "
                        f"Types were: {value_types}."
                    )
        except StopIteration:  # This means no types were found, value_types is empty
            raise MissingTypeError(
                f"Property '{name}' on '{owner}' is missing a type annotation. "
                "Please provide a type annotation ."
            )
        if len(value_types) == 1 and "model_argument" in value_types:
            raise MissingTypeError(
                f"Property '{name}' on '{owner}' specifies `model` but is not type annotated."
            )
        print(
            f"Initializing property '{name}' on '{owner}', {value_types}."
        )  # TODO: Debug print statement, remove
        # If the model is a plain type, wrap it in a RootModel so that it can be used
        # as a FastAPI model.
        self.model = wrap_plain_types_in_rootmodel(self._value_type)
        # Try to generate a DataSchema, so that we can raise an error that's easy to
        # link to the offending ThingProperty
        type_to_dataschema(self.model)

    @property
    def title(self):
        """A human-readable title"""
        if self._title:
            return self._title
        if self._getter and get_summary(self._getter):
            return get_summary(self._getter)
        return self.name

    @property
    def description(self):
        """A description of the property"""
        return self._description or get_docstring(self._getter, remove_summary=True)

    @overload
    def __get__(self, obj: None, owner: Type[Owner]) -> Self:
        """Called when an attribute is accessed via class not an instance"""

    @overload
    def __get__(self, obj: Owner, owner: Type[Owner] | None) -> Value:
        """Called when an attribute is accessed on an instance variable"""

    def __get__(
        self, obj: Owner | None, owner: Type[Owner] | None = None
    ) -> Value | Self:
        """The value of the property

        If `obj` is none (i.e. we are getting the attribute of the class),
        we return the descriptor.

        If no getter is set, we'll return either the initial value, or the value
        from the object's __dict__, i.e. we behave like a variable.

        If a getter is set, we will use it, unless the property is observable, at
        which point the getter is only ever used once, to set the initial value.
        """
        if obj is None:
            return self
        try:
            if self._getter and not self.observable:
                # if there's a getter and the property isn't observable, use it
                return self._getter(obj)
            # otherwise, behave like a variable and return our value
            return obj.__dict__[self.name]
        except KeyError:
            if self._getter:
                # if we get to here, the property should be observable, so cache
                obj.__dict__[self.name] = self._getter(obj)
                return obj.__dict__[self.name]
            elif not isinstance(self.initial_value, EllipsisType):
                return self.initial_value
            else:
                raise MissingDefaultError(
                    f"Property '{self.name}' on '{obj.__class__.__name__}' has "
                    " no value and no getter or initial value."
                )

    def __set__(self, obj, value):
        """Set the property's value"""
        obj.__dict__[self.name] = value
        if self._setter:
            self._setter(obj, value)
        self.emit_changed_event(obj, value)

    def _observers_set(self, obj):
        """A set used to notify changes"""
        ld = labthings_data(obj)
        if self.name not in ld.property_observers:
            ld.property_observers[self.name] = WeakSet()
        return ld.property_observers[self.name]

    def emit_changed_event(self, obj: Thing, value: Any) -> None:
        """Notify subscribers that the property has changed

        This function is run when properties are upadated. It must be run from
        within a thread. This could be the `Invocation` thread of a running action, or
        the property should be updated over via a client/http. It must be run from a
        thread as it is communicating with the event loop via an `asyncio` blocking
        portal.

        :raises NotConnectedToServerError: if the Thing that is calling the property
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

    async def emit_changed_event_async(self, obj: Thing, value: Any):
        """Notify subscribers that the property has changed"""
        for observer in self._observers_set(obj):
            await observer.send(
                {"messageType": "propertyStatus", "data": {self._name: value}}
            )

    @property
    def name(self):
        """The name of the property"""
        return self._name

    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add this action to a FastAPI app, bound to a particular Thing."""
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
            return self.__get__(thing, type(thing))

    def property_affordance(
        self, thing: Thing, path: Optional[str] = None
    ) -> PropertyAffordance:
        """Represent the property in a Thing Description."""
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

    def getter(self, func: Callable) -> Self:
        """set the function that gets the property's value"""
        self._getter = func
        return self

    def setter(self, func: Callable) -> Self:
        """Decorator to set the property's value

        ``ThingProperty`` descriptors return the value they hold
        when they are accessed. However, they can run code when they are set: this
        decorator sets a function as that code.
        """
        self._setter = func
        self.readonly = False
        return self


class ThingSetting(ThingProperty[Value], Generic[Value]):
    """A setting can be accessed via the HTTP API and is persistent between sessions

    A ThingSetting is a ThingProperty with extra functionality for triggering
    a Thing to save its settings.

    Note: If a setting is mutated rather than assigned to, this will not trigger saving.
    For example: if a Thing has a setting called `dictsetting` holding the dictionary
    `{"a": 1, "b": 2}` then `self.dictsetting = {"a": 2, "b": 2}` would trigger saving
    but `self.dictsetting[a] = 2` would not, as the setter for `dictsetting` is never
    called.

    The setting otherwise acts just like a normal variable.
    """

    def __set__(self, obj, value):
        """Set the property's value"""
        super().__set__(obj, value)
        obj.save_settings()

    def set_without_emit(self, obj, value):
        """Set the property's value, but do not emit event to notify the server

        This function is not expected to be used externally. It is called during
        initial setup so that the setting can be set from disk before the server
        is fully started.
        """
        obj.__dict__[self.name] = value
        if self._setter:
            self._setter(obj, value)
