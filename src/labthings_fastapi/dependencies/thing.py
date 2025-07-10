r"""FastAPI dependency to allow `.Thing`\ s to depend on each other.

This module defines a mechanism to obtain a `.DirectThingClient` that
wraps another `.Thing` on the same server. See things_from_things_ and
dependencies_ for more detail.

.. note::

    `.direct_thing_client_dependency` may confuse linters and type
    checkers, as types should not be the result of a function call.
    You may wish to manually create an annotated type using
    `.direct_thing_client_class`.
"""

from __future__ import annotations
from typing import Annotated, Optional

from fastapi import Depends

from ..thing import Thing
from ..client.in_server import direct_thing_client_class


def direct_thing_client_dependency(
    thing_class: type[Thing],
    thing_path: str,
    actions: Optional[list[str]] = None,
) -> type[Thing]:
    """Make an annotated type to allow Things to depend on each other.

    This function returns an annotated type that may be used as a FastAPI
    dependency. The dependency will return a `.DirectThingClient` that
    wraps the specified `.Thing`. This should be a drop-in replacement for
    `.ThingClient` so that code is consistent whether run in an action, or
    in a script or notebook on a remote computer.

    See things_from_things_ and dependencies_.

    .. note::

        `.direct_thing_client_dependency` may confuse linters and type
        checkers, as types should not be the result of a function call.
        You may wish to manually create an annotated type using
        `.direct_thing_client_class`.

    :param thing_class: The class of the thing to connect to
    :param thing_path: The path to the thing on the server
    :param actions: The actions that the client should be able to perform.
        If this is specified, only those actions will be available. If it is
        `None` (default), all actions will be available.

        Note that the dependencies of all available actions will be added to
        your endpoint - so it is best to only specify the actions you need, in
        order to avoid spurious extra dependencies.
    :return: A type annotation that will cause FastAPI to supply a direct thing client
    """
    C = direct_thing_client_class(thing_class, thing_path, actions=actions)
    return Annotated[C, Depends()]  # type: ignore[return-value]
