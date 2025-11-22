"""Mark the Interaction Affordances of a Thing.

LabThings generates a :ref:`wot_td` to allow actions, properties, and
events to be used by client code. The descriptions of each "interaction
affordance" (see :ref:`wot_affordances`) rely on docstrings and Python
type hints to provide a full description of the parameters, so it's
important that you use these effectively.



Actions
-------

You can add an Action to a Thing by declaring a method, decorated with
:deco:`.thing_action`. Parameters are not usually needed, but can be supplied to set
various options.

Properties
----------

As with Actions, Properties can be declared by decorating either a function, or
an attribute, with :deco:`.property`. You can use the decorator either on
a function (in which case that
function acts as the "getter" just like with Python's :deco:`property` decorator).

Events
------

Events are created by decorating attributes with :deco:`.thing_event`. Functions are
not supported at this time.
"""

from functools import wraps, partial
from typing import Any, Optional, Callable, overload
from ..descriptors import (
    ActionDescriptor,
)


def mark_thing_action(func: Callable, **kwargs: Any) -> ActionDescriptor:
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
def thing_action(func: Callable, **kwargs: Any) -> ActionDescriptor: ...


@overload
def thing_action(
    **kwargs: Any,
) -> Callable[
    [
        Callable,
    ],
    ActionDescriptor,
]: ...


@wraps(mark_thing_action)
def thing_action(
    func: Optional[Callable] = None, **kwargs: Any
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
