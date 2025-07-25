"""Mark the Interaction Affordances of a Thing.

See :ref:`wot_cc` for definitions of Interaction Affordance and other terms.

LabThings generates a :ref:`wot_td` to allow actions, properties, and
events to be used by client code. The descriptions of each "interaction
affordance" rely on docstrings and Python type hints to provide a full
description of the parameters, so it's important that you use these
effectively.

If you have a complex datatype, it's recommended to use a `pydantic` model
to describe it - this is often the case for complicated properties or events.
For actions, a model is created automatically based on the function's
signature: if you want to add descriptions or validators to individual
arguments, you may use `pydantic.Field` to do this.

Actions
-------

You can add an Action to a Thing by declaring a method, decorated with
:deco:`.thing_action`. Parameters are not usually needed, but can be supplied to set
various options.

Properties
----------

As with Actions, Properties can be declared by decorating either a function, or
an attribute, with :deco:`.thing_property`. You can use the decorator either on
a function (in which case that
function acts as the "getter" just like with Python's :deco`property` decorator).

Events
------

Events are created by decorating attributes with :deco:`.thing_event`. Functions are
not supported at this time.
"""

from functools import wraps, partial
from typing import Optional, Callable, overload
from ..descriptors import (
    ActionDescriptor,
    ThingProperty,
    ThingSetting,
    EndpointDescriptor,
    HTTPMethod,
)
from ..utilities.introspection import return_type


def mark_thing_action(func: Callable, **kwargs) -> ActionDescriptor:
    r"""Mark a method of a Thing as an Action.

    We replace the function with a descriptor that's a
    subclass of `.ActionDescriptor`

    :param func: The function to be decorated.
    :param \**kwargs: Additional keyword arguments are passed to the constructor
        of `.ActionDescriptor`.

    :return: An `.ActionDescriptor` wrapping the method.
    """

    class ActionDescriptorSubclass(ActionDescriptor):
        pass

    return ActionDescriptorSubclass(func, **kwargs)


@overload
def thing_action(func: Callable, **kwargs) -> ActionDescriptor: ...


@overload
def thing_action(
    **kwargs,
) -> Callable[
    [
        Callable,
    ],
    ActionDescriptor,
]: ...


@wraps(mark_thing_action)
def thing_action(
    func: Optional[Callable] = None, **kwargs
) -> (
    ActionDescriptor
    | Callable[
        [
            Callable,
        ],
        ActionDescriptor,
    ]
):
    r"""Mark a method of a `.Thing` as a LabThings Action.

    Methods decorated with :deco:`thing_action` will be available to call
    over HTTP as actions. See :ref:`actions` for an introduction to the concept
    of actions.

    This decorator may be used with or without arguments.

    :param func: The method to be decorated as an action.
    :param \**kwargs: Keyword arguments are passed to the constructor
        of `.ActionDescriptor`.

    :return: Whether used with or without arguments, the result is that
        the method is wrapped in an `.ActionDescriptor`, so it can be
        called as usual, but will also be exposed over HTTP.
    """
    # This can be used with or without arguments.
    # If we're being used without arguments, we will
    # have a non-None value for `func` and defaults
    # for the arguments.
    # If the decorator does have arguments, we must
    # return a partial object, which then calls the
    # wrapped function once.
    if func is not None:
        return mark_thing_action(func, **kwargs)
    else:
        return partial(mark_thing_action, **kwargs)


def thing_property(func: Callable) -> ThingProperty:
    """Mark a method of a Thing as a LabThings Property.

    This should be used as a decorator with a getter and a setter
    just like a standard python `property` decorator. If extra functionality
    is not required in the decorator, then using the `.ThingProperty` class
    directly may allow for clearer code

    Properties should always have a type annotation. This type annotation
    will be used in automatic documentation and also to serialise the value
    to JSON when it is sent over th network. This mean that the type of your
    property should either be JSON serialisable (i.e. simple built-in types)
    or a subclass of `pydantic.BaseModel`.

    :param func: A method to use as the getter for the new property.

    :return: A `.ThingProperty` descriptor that works like `property` but
        allows the value to be read over HTTP.
    """
    # Replace the function with a `Descriptor` that's a `ThingProperty`
    return ThingProperty(
        return_type(func),
        readonly=True,
        observable=False,
        getter=func,
    )


def thing_setting(func: Callable) -> ThingSetting:
    """Mark a method of a Thing as a LabThings Setting.

    A setting is a property that is saved to disk, so it persists even when
    the LabThings server is restarted.

    This should be used as a decorator with a getter and a setter
    just like a standard python property decorator. If extra functionality
    is not required in the decorator, then using the `ThingSetting` class
    directly may allow for clearer code where the property works like a
    variable.

    When creating a setting using this decorator, you must always add a setter
    as it is used to load the value from disk. This follows the same syntax as
    for `property`, i.e. a second function with the same name, decorated with
    ``@my_property_name.setter``.

    A type annotation is required, and should follow the same constraints as
    for :deco:`thing_property`.

    If the type is a pydantic BaseModel, then the setter must also be able to accept
    the dictionary representation of this BaseModel as this is what will be used to
    set the Setting when loading from disk on starting the server.

    .. note::
        If a setting is mutated rather than set, this will not trigger saving.
        For example: if a Thing has a setting called ``dictsetting`` holding the
        dictionary ``{"a": 1, "b": 2}`` then ``self.dictsetting = {"a": 2, "b": 2}``
        would trigger saving but ``self.dictsetting[a] = 2`` would not, as the
        setter for ``dictsetting`` is never called.

    :param func: A method to use as the getter for the new property.

    :return: A `.ThingSetting` descriptor that works like `property` but
        allows the value to be read over HTTP and saves it to disk.
    """
    # Replace the function with a `Descriptor` that's a `ThingSetting`
    return ThingSetting(
        return_type(func),
        readonly=True,
        observable=False,
        getter=func,
    )


def fastapi_endpoint(
    method: HTTPMethod, path: Optional[str] = None, **kwargs
) -> Callable[[Callable], EndpointDescriptor]:
    r"""Mark a function as a FastAPI endpoint without making it an action.

    This decorator will cause a method of a `.Thing` to be directly added to
    the HTTP API, bypassing the machinery underlying Action and Property
    affordances. Such endpoints will not be documented in the :ref:`wot_td` but
    may be used as the target of links. For example, this could allow a file
    to be downloaded from the `.Thing` at a known URL, or serve a video stream
    that wouldn't be supported as a `.Blob`\ .

    The majority of `.Thing` implementations won't need this decorator, but
    it is here to enable flexibility when it's needed.

    This decorator always takes arguments; in particular, ``method`` is
    required. It should be used as:

    .. code-block:: python

        class DownloadThing(Thing):
            @fastapi_endpoint("get")
            def plain_text_response(self) -> str:
                return "example string"

    This decorator is intended to work very similarly to the `fastapi` decorators
    ``@app.get``, ``@app.post``, etc., with two changes:

    1. The path is relative to the host `.Thing` and will default to the name
        of the method.
    2. The method will be called with the host `.Thing` as its first argument,
        i.e. it will be bound to the class as usua.

    :param method: The HTTP verb this endpoint responds to.
    :param path: The path, relative to the host `.Thing` base URL.
    :param \**kwargs: Additional keyword arguments are passed to the
        `fastapi.FastAPI.get` decorator if ``method`` is ``get``, or to
        the equivalent decorator for other HTTP verbs.

    :return: When used as intended, the result is an `.EndpointDescriptor`.
    """

    def decorator(func: Callable) -> EndpointDescriptor:
        return EndpointDescriptor(func, http_method=method, path=path, **kwargs)

    return decorator
