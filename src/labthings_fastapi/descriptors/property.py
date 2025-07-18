"""Define a descriptor to represent properties.

:ref:`wot_properties` are represented in LabThings by `.ThingProperty` descriptors.
These descriptors work similarly to regular Python properties or attributes,
with the addition of features that allow them to be accessed over HTTP and
documented in the :ref:`wot_td` and OpenAPI documents.

This module defines the `.ThingProperty` class.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Annotated, Any, Callable, Optional
from weakref import WeakSet

from typing_extensions import Self
from pydantic import BaseModel, RootModel
from fastapi import Body, FastAPI

from ..utilities import labthings_data, wrap_plain_types_in_rootmodel
from ..utilities.introspection import get_summary, get_docstring
from ..thing_description._model import PropertyAffordance, Form, DataSchema, PropertyOp
from ..thing_description import type_to_dataschema
from ..exceptions import NotConnectedToServerError


if TYPE_CHECKING:
    from ..thing import Thing


class ThingProperty:
    """A property that can be accessed via the HTTP API.

    By default, a ThingProperty acts like
    a normal variable, but functionality can be added in several ways.
    """

    model: type[BaseModel]
    readonly: bool = False

    def __init__(
        self,
        model: type,
        initial_value: Any = None,
        readonly: bool = False,
        observable: bool = False,
        description: Optional[str] = None,
        title: Optional[str] = None,
        getter: Optional[Callable] = None,
        setter: Optional[Callable] = None,
    ):
        """Create a property that can be accessed via the HTTP API.

        `.ThingProperty` is a descriptor that functions like a variable, optionally
        with notifications when it is set. It may also have a getter and setter,
        which work in a similar way to Python properties.

        `.ThingProperty` can behave in several different ways:

        * If no ``getter`` or ``setter`` is specified, it will behave like a simple
          data attribute (i.e. a variable). If ``observable`` is ``True``, it is
          possible to register for notifications when the value is set. In this
          case, an ``initial_value`` is required.
        * If a ``getter`` is specified and ``observable`` is ``False``, the ``getter``
          will be called when the property is accessed, and its return value
          will be the property's value, just like the builtin ``property``. The
          property will be read-only both locally and via HTTP.
        * If a ``getter`` is specified and ``observable`` is ``True``, the ``getter``
          is used instead of ``initial_value`` but thereafter the property
          behaves like a variable. The ``getter`` is only on first access.
          The property may be written to locally, and whether it's writable
          via HTTP depends on the ``readonly`` argument.
        * If both a ``getter`` and ``setter`` are specified and ``observable`` is
          ``False``,
          the property behaves like a Python property, with the ``getter`` being
          called when the property is accessed, and the ``setter`` being called
          when the property is set. The property is read-only via HTTP if
          ``readonly`` is ``True``. It may always be written to locally.
        * If ``observable`` is ``True`` and a ``setter`` is specified, the property
          will behave like a variable, but will call the ``setter``
          when the property is set. The ``setter`` may perform tasks like sending
          the updated value to the hardware, but it is not responsible for
          remembering the value. The initial value is set via the ``getter`` or
          ``initial_value``.


        :param model: The type of the property. This is optional, because it is
            better to use type hints (see notes on typing above).
        :param initial_value: The initial value of the property. If this is set,
            the property must not have a getter, and should behave like a variable.
        :param readonly: If True, the property cannot be set via the HTTP API.
        :param observable: If True, the property can be observed for changes via
            websockets. This causes the setter to run code in the async event loop
            that will notify a list of subscribers each time the property is set.
            Currently, only websockets can be used to observe properties.
        :param description: A description of the property, used in the API
            documentation. LabThings will attempt to take this from the docstring
            if not supplied.
        :param title: A human-readable title for the property, used in the API
            documentation. Defaults to the first line of the docstring, or the name
            of the property.
        :param getter: A function that gets the value of the property.
        :param setter: A function that sets the value of the property.

        :raise ValueError: if the initial value or type are missing or incorrectly
            specified.
        """
        if getter and initial_value is not None:
            raise ValueError("getter and an initial value are mutually exclusive.")
        if model is None:
            raise ValueError("LabThings Properties must have a type")
        self.model = wrap_plain_types_in_rootmodel(model)
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
        type_to_dataschema(self.model)

    def __set_name__(self, owner: type[Thing], name: str) -> None:
        """Take note of the name to which the descriptor is assigned.

        This is called when the descriptor is assigned to an attribute of a class.

        :param owner: the `.Thing` subclass to which we are being attached.
        :param name: the name to which we have been assigned.
        """
        self._name = name

    @property
    def title(self):
        """A human-readable title for the property."""
        if self._title:
            return self._title
        if self._getter and get_summary(self._getter):
            return get_summary(self._getter)
        return self.name

    @property
    def description(self):
        """A description of the property."""
        return self._description or get_docstring(self._getter, remove_summary=True)

    def __get__(self, obj: Thing | None, type: type | None = None) -> Any:
        """Return the value of the property.

        If `obj` is none (i.e. we are getting the attribute of the class),
        we return the descriptor.

        If no getter is set, we'll return either the initial value, or the value
        from the object's __dict__, i.e. we behave like a variable.

        If a getter is set, we will use it, unless the property is observable, at
        which point the getter is only ever used once, to set the initial value.

        :param obj: the `.Thing` to which we are attached.
        :param type: the class on which we are defined.

        :return: the value of the property (when accessed on an instance), or
            this descriptor if accessed as a class attribute.
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
            else:
                return self.initial_value

    def __set__(self, obj: Thing, value: Any) -> None:
        """Set the property's value.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value for the property.
        """
        obj.__dict__[self.name] = value
        if self._setter:
            self._setter(obj, value)
        self.emit_changed_event(obj, value)

    def _observers_set(self, obj: Thing):
        """Return the observers of this property.

        Each observer in this set will be notified when the property is changed.
        See ``.ThingProperty.emit_changed_event``

        :param obj: the `.Thing` to which we are attached.

        :return: the set of observers corresponding to ``obj``.
        """
        ld = labthings_data(obj)
        if self.name not in ld.property_observers:
            ld.property_observers[self.name] = WeakSet()
        return ld.property_observers[self.name]

    def emit_changed_event(self, obj: Thing, value: Any) -> None:
        """Notify subscribers that the property has changed.

        This function is run when properties are upadated. It must be run from
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

    async def emit_changed_event_async(self, obj: Thing, value: Any):
        """Notify subscribers that the property has changed.

        This function may only be run in the `anyio` event loop. See
        `.ThingProperty.emit_changed_event`.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new property value, to be sent to observers.
        """
        for observer in self._observers_set(obj):
            await observer.send(
                {"messageType": "propertyStatus", "data": {self._name: value}}
            )

    @property
    def name(self):
        """The name of the property.

        This should be consistent between the class definition and the
        :ref:`wot_td` as well as appearing in the URLs for getting and setting.
        """
        return self._name

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
        self, thing: Thing, path: Optional[str] = None
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

    def getter(self, func: Callable) -> Self:
        """Set the function that gets the property's value.

        :param func: is the new getter function.

        :return: this property (to allow its use as a decorator).
        """
        self._getter = func
        return self

    def setter(self, func: Callable) -> Self:
        """Change the setter function.

        `.ThingProperty` descriptors return the value they hold
        when they are accessed. However, they can run code when they are set: this
        decorator sets a function as that code.

        :param func: is the new setter function.

        :return: this property (to allow its use as a decorator).
        """
        self._setter = func
        self.readonly = False
        return self


class ThingSetting(ThingProperty):
    """A `.ThingProperty` that persists on disk.

    A setting can be accessed via the HTTP API and is persistent between sessions.

    A `.ThingSetting` is a `.ThingProperty` with extra functionality for triggering
    a `.Thing` to save its settings.

    Note: If a setting is mutated rather than assigned to, this will not trigger saving.
    For example: if a Thing has a setting called `dictsetting` holding the dictionary
    `{"a": 1, "b": 2}` then `self.dictsetting = {"a": 2, "b": 2}` would trigger saving
    but `self.dictsetting[a] = 2` would not, as the setter for `dictsetting` is never
    called.

    The setting otherwise acts just like a normal variable.
    """

    def __set__(self, obj: Thing, value: Any):
        """Set the setting's value.

        This will cause the settings to be saved to disk.

        :param obj: the `.Thing` to which we are attached.
        :param value: the new value of the setting.
        """
        super().__set__(obj, value)
        obj.save_settings()

    def set_without_emit(self, obj: Thing, value: Any):
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
