"""A mock client that uses a Thing directly.

Currently this is not a subclass of ThingClient, that may need to change.
It's a good idea to create a DirectThingClient at module level, so that type
hints work.

This module may get moved in the near future.

"""

from __future__ import annotations
from functools import wraps
import inspect
import logging
from typing import Any, Mapping, Optional, Union
from pydantic import BaseModel
from labthings_fastapi.descriptors.action import ActionDescriptor

from labthings_fastapi.descriptors.property import PropertyDescriptor
from labthings_fastapi.utilities import attributes
from . import PropertyClientDescriptor
from ..thing import Thing
from ..server import find_thing_server
from fastapi import Request


class DirectThingClient:
    __globals__ = globals()  # "bake in" globals so dependency injection works
    thing_class: type[Thing]
    thing_path: str

    def __init__(self, request: Request, **dependencies: Mapping[str, Any]):
        """Wrapper for a Thing that makes it work like a ThingClient

        This class is designed to be used as a FastAPI dependency, and will retrieve a
        Thing based on its `thing_path` attribute. Finding the Thing by class may also
        be an option in the future.
        """
        server = find_thing_server(request.app)
        self._wrapped_thing = server.things[self.thing_path]
        self._request = request
        self._dependencies = dependencies


def property_descriptor(
    property_name: str,
    model: Union[type, BaseModel],
    description: Optional[str] = None,
    readable: bool = True,
    writeable: bool = True,
    property_path: Optional[str] = None,
) -> PropertyClientDescriptor:
    """Create a correctly-typed descriptor that gets and/or sets a property

    This is copy-pasted from labthings_fastapi.client.__init__.property_descriptor
    TODO: refactor this into a shared function.
    """

    class P(PropertyClientDescriptor):
        name = property_name
        type = model
        path = property_path or property_name

    def __get__(
        self,
        obj: Optional[DirectThingClient] = None,
        _objtype: Optional[type[DirectThingClient]] = None,
    ):
        if obj is None:
            return self
        return getattr(obj._wrapped_thing, self.name)

    def __set__(self, obj: DirectThingClient, value: Any):
        setattr(obj._wrapped_thing, self.name, value)

    if readable:
        __get__.__annotations__["return"] = model
        P.__get__ = __get__  # type: ignore[attr-defined]
    if writeable:
        __set__.__annotations__["value"] = model
        P.__set__ = __set__  # type: ignore[attr-defined]
    if description:
        P.__doc__ = description
    return P()


def add_action(
    attrs: dict[str, Any],
    dependencies: list[inspect.Parameter],
    name: str,
    action: ActionDescriptor,
) -> None:
    """Generates an action method and adds it to an attrs dict

    FastAPI Dependencies are appended to the `dependencies` list.
    """

    @wraps(action.func)
    def action_method(self, **kwargs):
        dependency_kwargs = {
            param.name: self._dependencies[param.name]
            for param in action.dependency_params
        }
        kwargs_and_deps = {**kwargs, **dependency_kwargs}
        return getattr(self._wrapped_thing, name)(**kwargs_and_deps)

    attrs[name] = action_method
    # We collect up all the dependencies, so that we can
    # resolve them when we create the client.
    for param in action.dependency_params:
        included = False
        for existing_param in dependencies:
            if existing_param.name == param.name:
                # Currently, each name may only have one annotation, across
                # all actions - this is a limitation we should fix.
                if existing_param.annotation != param.annotation:
                    raise ValueError(
                        f"Conflicting dependency injection for {param.name}"
                    )
                included = True
        if not included:
            dependencies.append(param)


def add_property(
    attrs: dict[str, Any], property_name: str, property: PropertyDescriptor
) -> None:
    """Add a property to a DirectThingClient subclass"""
    attrs[property_name] = property_descriptor(
        property_name,
        property.model,
        description=property.description,
        writeable=not property.readonly,
        readable=True,  # TODO: make this configurable in PropertyDescriptor
    )


def direct_thing_client_class(
    thing_class: type[Thing],
    thing_path: str,
    actions: Optional[list[str]] = None,
):
    """Create a DirectThingClient from a Thing class and a path

    This is a class, not an instance: it's designed to be a FastAPI dependency.
    """

    def init_proxy(self, request: Request, **dependencies: Mapping[str, Any]):
        f"""A client for {thing_class} at {thing_path}"""
        # NB this definition isimportant, as we must modify its signature.
        # Inheriting __init__ means we'll accidentally modify the signature
        # of `DirectThingClient` with bad results.
        DirectThingClient.__init__(self, request, **dependencies)

    # Using a class definition gets confused by the scope of the function
    # arguments - this is equivalent to a class definition but all the
    # arguments are evaluated in the right scope.
    client_attrs = {
        "thing_class": thing_class,
        "thing_path": thing_path,
        "__doc__": f"A client for {thing_class} at {thing_path}",
        "__init__": init_proxy,
    }
    dependencies: list[inspect.Parameter] = []
    for name, item in attributes(thing_class):
        if isinstance(item, PropertyDescriptor):
            # TODO: What about properties that don't use descriptors? Fall back to http?
            add_property(client_attrs, name, item)
        elif isinstance(item, ActionDescriptor):
            if actions is None or name in actions:
                add_action(client_attrs, dependencies, name, item)
            else:
                continue  # Ignore actions that aren't in the list
        else:
            for affordance in ["property", "action", "event"]:
                if hasattr(item, f"{affordance}_affordance"):
                    logging.warning(
                        f"DirectThingClient doesn't support custom affordances, "
                        f"ignoring {name}"
                    )
    # This block of code makes dependencies show up in __init__ so
    # they get resolved. It's more or less copied from the `action` descriptor.
    sig = inspect.signature(init_proxy)
    params = [p for p in sig.parameters.values() if p.name != "dependencies"]
    init_proxy.__signature__ = sig.replace(  # type: ignore[attr-defined]
        parameters=params + dependencies
    )
    return type(
        f"{thing_class.__name__}DirectClient", (DirectThingClient,), client_attrs
    )
