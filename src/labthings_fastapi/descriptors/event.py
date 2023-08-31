"""
Define an object to represent an Action, as a descriptor.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
from pydantic import BaseModel
from fastapi import FastAPI
from anyio.abc import ObjectSendStream
from weakref import WeakSet, ref
from ..utilities import wrap_plain_types_in_rootmodel
from ..utilities.autoinitialising_descriptor import AutoinitialisingDescriptor
from ..thing_description.model import PropertyAffordance
from ..thing_description import type_to_dataschema


if TYPE_CHECKING:
    from ..thing import Thing


class EventDescriptor(AutoinitialisingDescriptor[Thing, Event]):
    """A property that can be subscribed to via the HTTP API
    
    For now, only WebSocket subscriptions will be supported
    """
    #TODO: common subclass with PropertyDescriptor
    model: type[BaseModel]
    def __init__(
            self, 
            model: type, 
            description: Optional[str] = None,
            title: Optional[str] = None,
        ):
        if model is None:
            raise ValueError("LabThings Events must have a type")
        self.model = wrap_plain_types_in_rootmodel(model)
        self.description = description
        self.title = title
        if self.description and not self.title:
            self.title = self.description.partition("\n")[0]
        # Try to generate a DataSchema, so that we can raise an error that's easy to
        # link to the offending PropertyDescriptor
        type_to_dataschema(self.model)

    def __set_name__(self, owner, name: str):
        self._name = name
        if not self.title:
            self.title = name

    def initial_value(self, obj: Thing) -> Event:
        return Event(
            name=self.name,
            thing=obj,
            model=self.model,
        )
    
    def add_to_fastapi(self, app: FastAPI, thing: Thing):
        """Add this event to a FastAPI app, bound to a particular Thing."""
        @app.get(
            thing.path + self.name,
            response_model=self.model,
            response_description=f"Event {self.name}",
            summary=self.title,
            description=(
                f"## {self.title}\n\n{self.description or ''}\n\n"
                "Events are currently only supported through the websocket "
                "endpoint."
            )
        )
        def get_property():
            raise NotImplementedError()

    def event_affordance(
            self, thing: Thing, path: Optional[str]=None
        ) -> PropertyAffordance:
        """Represent the property in a Thing Description."""
        path = path or thing.path
        raise NotImplementedError()
   

class Event:
    """Manage an event emitted from a particular Thing instance"""
    def __init__(self, name: str, thing: Thing, model: type[BaseModel]):
        self._name = name
        self._thing = ref(thing)
        self.model = model
        self._observers: WeakSet[ObjectSendStream] = WeakSet()

    def emit(self, value: Any) -> None:
        """Notify subscribers that the property has changed
        
        NB this function **must** be run from a thread, not the event loop.
        """
        runner = self.thing._labthings_blocking_portal
        if not runner:
            raise RuntimeError("Can't emit without a blocking portal")
        runner.start_task_soon(self.emit_async, value)

    async def emit_async(self, value: Any):
        """Notify subscribers that the property has changed
        
        This generates notifications in a format consistent with WebThings
        https://webthings.io/api/#event-message
        """
        for observer in self._observers:
            await observer.send(
                {
                    "messageType": "event",
                    "data": {
                        self._name: value
                    }
                }
            )
    
    @property
    def name(self):
        """The name of the event"""
        return self._name
    
    @property
    def thing(self):
        """The `Thing` we are attached to.
        
        We store only a weak reference, to avoid circular referencing that will
        cause problems with garbage collection.
        """
        return self._thing()
