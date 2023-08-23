"""A first pass at a client library for LabThings-FastAPI

This will become its own package if it's any good. The goal is to see if we can
make a client library that produces introspectable Python objects from a Thing
Description.
"""

from __future__ import annotations
import json
from typing import Any, Callable, Optional, Union
import httpx

from pydantic import BaseModel

class PropertyClientDescriptor:
    pass

class ThingClient:
    def __init__(self, base_uri: str):
        self.base_uri = base_uri
        self.client = httpx.Client() 

    def get_property(self, path: str) -> Any:
        r = self.client.get(self.base_uri + path)
        r.raise_for_status()
        return r.json()
    
    def set_property(self, path: str, value: Any):
        r = self.client.post(self.base_uri + path, json=value)
        r.raise_for_status()

    def invoke_action(self, path: str, **kwargs):
        r = self.client.post(self.base_uri + path, json=kwargs)
        r.raise_for_status()
        return r.json()

def property_descriptor(
        property_name: str,
        model: Union[type, BaseModel],
        description: Optional[str]=None,
        readable: bool=True,
        writeable: bool=True,
        property_path: Optional[str]=None,
    ) -> PropertyClientDescriptor:
        """Create a correctly-typed descriptor that gets and/or sets a property"""
        class P(PropertyClientDescriptor):
            name = property_name
            type = model
            path = property_path or property_name
        if readable:
            def __get__(
                    self,
                    obj: Optional[ThingClient]=None,
                    _objtype: Optional[type[ThingClient]]=None
                ):
                return obj.get_property(self.name)
            __get__.__annotations__["return"] = model
            P.__get__ = __get__
        if writeable:
            def __set__(
                    self,
                    obj: ThingClient,
                    value: Any
                ):
                obj.set_property(self.name, value)
            __set__.__annotations__["value"] = model
            P.__set__ = __set__
        if description:
            P.__doc__ = description
        return P()


def add_action(cls: type[ThingClient], action_name: str, action: dict):
    """Add an action to a ThingClient subclass"""
    def action_method(self, **kwargs):
        return self.invoke_action(action_name, **kwargs)
    if "output" in action and "type" in action["output"]:
        action_method.__annotations__["return"] = action["output"]["type"]
    if "description" in action:
        action_method.__doc__ = action["description"]
    setattr(cls, action_name, action_method)

def add_property(cls: type[ThingClient], property_name: str, property: dict):
    """Add a property to a ThingClient subclass"""
    setattr(
            cls,
            property_name,
            property_descriptor(
                property_name,
                property.get("type", Any),
                description = property.get("description", None),
                writeable = not property.get("readOnly", False),
                readable = not property.get("writeOnly", False),
            )
        )


def thing_client_class(thing_description: dict):
    """Create a ThingClient from a Thing Description"""
    class Client(ThingClient):
        pass

    for name, p in thing_description["properties"].items():
        add_property(Client, name, p)
    for name, a in thing_description["actions"].items():
        add_action(Client, name, a)
    return Client

def thing_client_from_url(thing_url: str) -> ThingClient:
    """Create a ThingClient from a URL"""
    r = httpx.get(thing_url)
    r.raise_for_status()
    return thing_client_class(r.json())(thing_url)