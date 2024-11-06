"""
Context Var access to the Action Manager

This module provides a context var to access the Action Manager instance.
While LabThings tries pretty hard to conform to FastAPI's excellent convention
that everything should be passed as a parameter, there are some cases where
that's hard. In particular, generating URLs when responses are serialised is
difficult, because `pydantic` doesn't have a way to pass in extra context.

If an endpoint uses the `ActionManagerDep` dependency, then the Action Manager
is available using `ActionManagerContext.get()`.
"""

from __future__ import annotations

from contextvars import ContextVar

from typing import Annotated
from typing_extensions import TypeAlias
from fastapi import Depends, Request
from ..dependencies.thing_server import find_thing_server
from ..actions import ActionManager


def action_manager_from_thing_server(request: Request) -> ActionManager:
    """Retrieve the Action Manager from the Thing Server

    This is for use as a FastAPI dependency, so the thing server is
    retrieved from the request object.
    """
    action_manager = find_thing_server(request.app).action_manager
    if action_manager is None:
        raise RuntimeError("Could not get the blocking portal from the server.")
    return action_manager


ActionManagerDep = Annotated[ActionManager, Depends(action_manager_from_thing_server)]
"""
A ready-made dependency type for the `ActionManager` object.
"""


ActionManagerContext = ContextVar[ActionManager]("ActionManagerContext")


async def make_action_manager_context_available(action_manager: ActionManagerDep):
    """Make the Action Manager available in the context

    The action manager may be accessed using `ActionManagerContext.get()`.
    """
    ActionManagerContext.set(action_manager)
    yield action_manager


ActionManagerContextDep: TypeAlias = Annotated[
    ActionManager, Depends(make_action_manager_context_available)
]
