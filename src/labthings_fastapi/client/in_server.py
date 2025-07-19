"""A mock client that uses a Thing directly.

When `.Thing` objects interact on the server, it can be very useful to
use an interface that is identical to the `.ThingClient` used to access
the same `.Thing` remotely. This means that code can run either on the
server or on a client, e.g. in a Jupyter notebook where it is much
easier to debug. See :ref:`things_from_things` for more detail.

Currently `.DirectThingClient` is not a subclass of `.ThingClient`,
that may need to change. It's a good idea to create a
`.DirectThingClient` at module level, so that type hints work.


"""

from __future__ import annotations
from functools import wraps
import inspect
import logging
from typing import Any, Mapping, Optional, Union
from pydantic import BaseModel
from ..descriptors.action import ActionDescriptor

from ..descriptors.property import ThingProperty
from ..utilities import attributes
from . import PropertyClientDescriptor
from ..thing import Thing
from ..dependencies.thing_server import find_thing_server
from fastapi import Request


__all__ = ["DirectThingClient", "direct_thing_client_class"]


class DirectThingClient:
    """A wrapper for `.Thing` that is a work-a-like for `.ThingClient`.

    This class is used to create a class that works like `.ThingClient`
    but does not communicate over HTTP. Instead, it wraps a `.Thing` object
    and calls its methods directly.

    It is not yet 100% identical to `.ThingClient`, in particular `.ThingClient`
    returns a lot of data directly as deserialised from JSON, while this class
    generally returns `pydantic.BaseModel` instances, without serialisation.

    `.DirectThingClient` is generally not used on its own, but is subclassed
    (often dynamically) to add the actions and properties of a particular
    `.Thing`.
    """

    __globals__ = globals()  # "bake in" globals so dependency injection works
    thing_class: type[Thing]
    """The class of the underlying `.Thing` we are wrapping."""
    thing_path: str
    """The path to the Thing on the server. Relative to the server's base URL."""

    def __init__(self, request: Request, **dependencies: Mapping[str, Any]):
        r"""Wrap a `.Thing` so it works like a `.ThingClient`.

        This class is designed to be used as a FastAPI dependency, and will
        retrieve a `.Thing` based on its ``thing_path`` attribute.
        Finding the Thing by class may also be an option in the future.

        :param request: This is a FastAPI dependency to access the
            `fastapi.Request` object, allowing access to various resources.
        :param \**dependencies: Further arguments will be added
            dynamically by subclasses, by duplicating this method and
            manipulating its signature. Adding arguments with annotated
            type hints instructs FastAPI to inject dependency arguments,
            such as access to other `.Things`.
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
    """Create a correctly-typed descriptor that gets and/or sets a property.

    .. todo::
        This is copy-pasted from labthings_fastapi.client.__init__.property_descriptor
        TODO: refactor this into a shared function.

    Create a descriptor object that wraps a property. This is for use on
    a `.DirectThingClient` subclass.

    :param property_name: should be the name of the property (i.e. the
        name it takes in the thing description, and also the name it is
        assigned to in the class).
    :param model: the Python ``type`` or a ``pydantic.BaseModel`` that
        represents the datatype of the property.
    :param description: text to use for a docstring.
    :param readable: whether the property may be read (i.e. has ``__get__``).
    :param writeable: whether the property may be written to.
    :param property_path: the URL of the ``getproperty`` and ``setproperty``
        HTTP endpoints. Currently these must both be the same. These are
        relative to the ``base_url``, i.e. the URL of the Thing Description.

    :return: a descriptor allowing access to the specified property.
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


class DependencyNameClashError(KeyError):
    """A dependency argument name is used inconsistently.

    A current limitation of `.DirectThingClient` is that the dependency
    arguments (see :ref:`dependencies`) are collected together in a single
    dictionary. This makes the assumption that, if a name is reused, it is
    reused for the same dependency.

    When names are reused, we check if the values match. If not, this
    exception is raised.
    """

    def __init__(self, name: str, existing: type, new: type):
        """Create a DependencyNameClashError.

        See class docstring for an explanation of the error.

        :param name: the name of the clashing dependencies.
        :param existing: the dependency type annotation in the dictionary.
        :param new: the clashing type annotation.
        """
        super().__init__(
            f"{self.__doc__}\n\n"
            f"This clash is with name: {name}.\n"
            f"Its value is currently {existing}, which clashes with {new}."
        )


def add_action(
    attrs: dict[str, Any],
    dependencies: list[inspect.Parameter],
    name: str,
    action: ActionDescriptor,
) -> None:
    """Generate an action method and adds it to an attrs dict.

    FastAPI Dependencies are appended to the `dependencies` list.
    This list should later be converted to type hints on the class
    initialiser, so that FastAPI supplies the dependencies when
    the `.DirectThingClient` is initialised.

    :param attrs: the attributes of a soon-to-be-created `.DirectThingClient`
        subclass. This will be passed to `type()` to create the subclass.
        We will add the action method to this dictionary.
    :param dependencies: lists the dependency parameters that will be
        injected by FastAPI as arguments to the class ``__init__``.
        Any dependency parameters of the supplied ``action`` should be
        added to this list.
    :param name: the name of the action. Should be the name of the
        attribute, i.e. we will set ``attrs[name]``, and also match
        the ``name`` in the supplied action descriptor.
    :param action: an `.ActionDescriptor` to be wrapped.

    :raise DependencyNameClashError: if dependencies are inconsistent.
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
                    raise DependencyNameClashError(
                        param.name, existing_param.annotation, param.annotation
                    )
                included = True
        if not included:
            dependencies.append(param)


def add_property(
    attrs: dict[str, Any], property_name: str, property: ThingProperty
) -> None:
    """Add a property to a DirectThingClient subclass.

    We create a new descriptor using `.property_descriptor` and add it
    to the ``attrs`` dictionary as ``property_name``.

    :param attrs: the attributes of a soon-to-be-created `.DirectThingClient`
        subclass. This will be passed to `type()` to create the subclass.
        We will add the property to this dictionary.
    :param property_name: the name of the property. Should be the name of the
        attribute, i.e. we will set ``attrs[name]``.
    :param property: a `.PropertyDescriptor` to be wrapped.
    """
    attrs[property_name] = property_descriptor(
        property_name,
        property.model,
        description=property.description,
        writeable=not property.readonly,
        readable=True,  # TODO: make this configurable in ThingProperty
    )


def direct_thing_client_class(
    thing_class: type[Thing],
    thing_path: str,
    actions: Optional[list[str]] = None,
) -> type[DirectThingClient]:
    r"""Create a DirectThingClient from a Thing class and a path.

    This is a class, not an instance: it's designed to be a FastAPI dependency.

    :param thing_class: The `.Thing` subclass that will be wrapped.
    :param thing_path: The path where the `.Thing` is found on the server.
    :param actions: An optional list giving a subset of actions that will be
        accessed. If this is specified, it may reduce the number of FastAPI
        dependencies we need.

    :return: a subclass of `DirectThingClient` with attributes that match the
        properties and actions of ``thing_class``. The ``__init__`` method
        will have annotations that instruct FastAPI to supply all the
        dependencies needed by its actions.

        This class may be used as a FastAPI dependency: see :ref:`things_from_things`.
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
        if isinstance(item, ThingProperty):
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
