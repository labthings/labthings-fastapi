"""
The decorators in this module mark the Interaction Affordances of a Thing.

LabThings generates a "Thing Description" to allow actions, properties, and
events to be used by client code. The descriptions of each "interaction
affordance" rely on docstrings and Python type hints to provide a full
description of the parameters, so it's important that you use these
effectively.

If you have a complex datatype, it's recommended to use a `pydantic` model
to describe it - this is often the case for complicated properties or events.
For actions, a model is created automatically based on the function's
signature: if you want to add descriptions or validators to individual
arguments, you may use `pydantic.Field` to do this.

## Actions

You can add an Action to a Thing by declaring a method, decorated with
`@thing_action`. Parameters are not usually needed, but can be supplied to set
various options.

## Properties

As with Actions, Properties can be declared by decorating either a function, or
an attribute, with `@thing_property`. You can use the decorator either on
a function (in which case that
function acts as the "getter" just like with Python's `@property` decorator).

## Events

Events are created by decorating attributes with `@thing_event`. Functions are
not supported at this time.
"""

from functools import wraps, partial
from typing import Optional, Callable
from ..descriptors import (
    ActionDescriptor,
    PropertyDescriptor,
    EndpointDescriptor,
    HTTPMethod,
)
from ..utilities.introspection import return_type


def mark_thing_action(func: Callable, **kwargs) -> ActionDescriptor:
    """Mark a method of a Thing as an Action

    We replace the function with a `Descriptor` that's a
    subclass of `ActionDescriptor`
    """

    class ActionDescriptorSubclass(ActionDescriptor):
        pass

    return ActionDescriptorSubclass(func, **kwargs)


@wraps(mark_thing_action)
def thing_action(func: Optional[Callable] = None, **kwargs):
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


def thing_property(func: Callable) -> PropertyDescriptor:
    """Mark a method of a Thing as a Property

    We replace the function with a `Descriptor` that's a
    subclass of `PropertyDescriptor`

    TODO: try https://stackoverflow.com/questions/54413434/type-hinting-with-descriptors
    """

    class PropertyDescriptorSubclass(PropertyDescriptor):
        def __get__(self, obj, objtype=None):
            return super().__get__(obj, objtype)

    return PropertyDescriptorSubclass(
        return_type(func),
        readonly=True,
        observable=False,
        getter=func,
    )


def fastapi_endpoint(method: HTTPMethod, path: Optional[str] = None, **kwargs):
    """Add a function to FastAPI as an endpoint"""

    def decorator(func):
        return EndpointDescriptor(func, http_method=method, path=path, **kwargs)

    return decorator
