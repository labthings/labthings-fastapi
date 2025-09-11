"""Context Var access to the Action Manager.

This module provides a context var to access the Action Manager instance.
While LabThings tries pretty hard to conform to FastAPI's excellent convention
that everything should be passed as a parameter, there are some cases where
that's hard. In particular, generating URLs when responses are serialised is
difficult, because `pydantic` doesn't have a way to access the `fastapi.Request`
object and use `fastapi.Request.url_for`.

If an endpoint uses the `.ActionManagerDep` dependency, then the `.ActionManager`
is supplied as an argument. More usefully, when the output is serialised the
`.ActionManager` is available using `.ActionManagerContext.get()`.

This is currently only used by `.Blob` objects, as "serialising" a `.Blob`
involves adding it to the `.ActionManager` and generating a download URL.
"""

from __future__ import annotations

from contextvars import ContextVar

from typing import Annotated, AsyncGenerator
from typing_extensions import TypeAlias
from fastapi import Depends, Request
from ..dependencies.thing_server import find_thing_server
from ..actions import ActionManager


def action_manager_from_thing_server(request: Request) -> ActionManager:
    r"""Retrieve the Action Manager from the Thing Server.

    This is for use as a FastAPI dependency. We use the ``request`` to
    access the `.ThingServer` and thus access the `.ActionManager`\ .

    :param request: the FastAPI request object. This will be supplied by
        FastAPI when this function is used as a dependency.

    :return: the `.ActionManager` object associated with our `.ThingServer`\ .
    """
    return find_thing_server(request.app).action_manager


ActionManagerDep = Annotated[ActionManager, Depends(action_manager_from_thing_server)]
"""
A ready-made dependency type for the `ActionManager` object.
"""


ActionManagerContext = ContextVar[ActionManager]("ActionManagerContext")


async def make_action_manager_context_available(
    action_manager: ActionManagerDep,
) -> AsyncGenerator[ActionManager]:
    """Make the Action Manager available in the context variable.

    The action manager may be accessed using `ActionManagerContext.get()` within
    this context manager.

    :param action_manager: The `.ActionManager` object. Note that this is an
        annotated type so it will be supplied automatically when used as a FastAPI
        dependency.

    :yield: the `.ActionManager` object.
    """
    ActionManagerContext.set(action_manager)
    yield action_manager


ActionManagerContextDep: TypeAlias = Annotated[
    ActionManager, Depends(make_action_manager_context_available)
]
