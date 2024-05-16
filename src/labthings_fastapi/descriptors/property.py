"""
Define an object to represent an Action, as a descriptor.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Annotated, Any, Callable, Optional
from typing_extensions import Self
from labthings_fastapi.utilities.introspection import get_summary, get_docstring
from pydantic import BaseModel, RootModel
from fastapi import Body, FastAPI
from weakref import WeakSet
from ..utilities import labthings_data, wrap_plain_types_in_rootmodel
from ..thing_description.model import PropertyAffordance, Form, DataSchema, PropertyOp
from ..thing_description import type_to_dataschema


if TYPE_CHECKING:
    from ..thing import Thing


class PropertyDescriptor:
    """A property that can be accessed via the HTTP API

    By default, a PropertyDescriptor is "dumb", i.e. it acts just like
    a normal variable.
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
        # link to the offending PropertyDescriptor
        type_to_dataschema(self.model)

    def __set_name__(self, owner, name: str):
        self._name = name

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

    def __get__(self, obj, type=None) -> Any:
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
            else:
                return self.initial_value

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

        NB this function **must** be run from a thread, not the event loop.
        """
        runner = obj._labthings_blocking_portal
        if not runner:
            raise RuntimeError("Can't emit without a blocking portal")
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
            return self.__get__(thing)

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

        PropertyDescriptors are variabes - so they will return the value they hold
        when they are accessed. However, they can run code when they are set: this
        decorator sets a function as that code.
        """
        self._setter = func
        self.readonly = False
        return self
