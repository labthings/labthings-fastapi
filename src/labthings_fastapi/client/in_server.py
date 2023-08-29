"""A mock client that uses a Thing directly.

Currently this is not a subclass of ThingClient, that may need to change.
It's a good idea to create a DirectThingClient at module level, so that type
hints work.

This module may get moved in the near future.

"""
from __future__ import annotations
from functools import wraps
import logging
from typing import Any, Optional, Union
from pydantic import BaseModel
from labthings_fastapi.descriptors.action import ActionDescriptor

from labthings_fastapi.descriptors.property import PropertyDescriptor
from labthings_fastapi.utilities import attributes
from . import PropertyClientDescriptor
from ..thing import Thing
from ..thing_server import find_thing_server
from fastapi import Request

class DirectThingClient:
    __globals__ = globals()  # "bake in" globals so dependency injection works
    thing_class: type[Thing] = None
    thing_path: Optional[str] = None
    def __init__(self, request: Request):
        """Wrapper for a Thing that makes it work like a ThingClient
        
        This class is designed to be used as a FastAPI dependency, and will retrieve a
        Thing based on its `thing_path` attribute. Finding the Thing by class may also
        be an option in the future.
        """
        server = find_thing_server(request.app)
        self._wrapped_thing = server.things[self.thing_path]

def property_descriptor(
        property_name: str,
        model: Union[type, BaseModel],
        description: Optional[str]=None,
        readable: bool=True,
        writeable: bool=True,
        property_path: Optional[str]=None,
    ) -> PropertyClientDescriptor:
        """Create a correctly-typed descriptor that gets and/or sets a property
        
        This is copy-pasted from labthings_fastapi.client.__init__.property_descriptor
        TODO: refactor this into a shared function.
        """
        class P(PropertyClientDescriptor):
            name = property_name
            type = model
            path = property_path or property_name
        if readable:
            def __get__(
                    self,
                    obj: Optional[DirectThingClient]=None,
                    _objtype: Optional[type[DirectThingClient]]=None
                ):
                if obj is None:
                    return self
                return getattr(obj._wrapped_thing, self.name)
            __get__.__annotations__["return"] = model
            P.__get__ = __get__  # type: ignore[attr-defined]
        if writeable:
            def __set__(
                    self,
                    obj: DirectThingClient,
                    value: Any
                ):
                setattr(obj, self.name, value)
            __set__.__annotations__["value"] = model
            P.__set__ = __set__  # type: ignore[attr-defined]
        if description:
            P.__doc__ = description
        return P()


def add_action(cls: type[DirectThingClient], action_name: str, function: callable):
    """Add an action to a DirectThingClient subclass"""
    @wraps(function)
    def action_method(self, **kwargs):
        return getattr(self._wrapped_thing, action_name)(**kwargs)
    setattr(cls, action_name, action_method)


def add_property(
        cls: type[DirectThingClient],
        property_name: str,
        property: PropertyDescriptor
    ):
    """Add a property to a DirectThingClient subclass"""
    setattr(
            cls,
            property_name,
            property_descriptor(
                property_name,
                property.model,
                description = property.description,
                writeable = not property.readonly,
                readable = True,  #TODO: make this configurable in PropertyDescriptor
            )
        )
    
def direct_thing_client(thing_class: type[Thing], thing_path: str):
    """Create a DirectThingClient from a Thing class and a path
    
    This is a class, not an instance: it's designed to be a FastAPI dependency.
    """
    class Client(DirectThingClient):
        pass
    Client.thing_class = thing_class
    Client.thing_path = thing_path
    for name, item in attributes(thing_class):
        if isinstance(item, PropertyDescriptor):
            # TODO: What about properties that don't use descriptors? Fall back to http?
            add_property(Client, name, item)
        elif isinstance(item, ActionDescriptor):
            add_action(Client, name, item)
        else:
            for affordance in ["property", "action", "event"]:
                if hasattr(item, f"{affordance}_affordance"):
                    logging.warning(
                        f"DirectThingClient doesn't support custom afforcances, "
                        f"ignoring {name}"
                    )
    return Client