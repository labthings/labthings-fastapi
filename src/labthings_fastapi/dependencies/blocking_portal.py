"""FastAPI dependency for a blocking portal

This allows dependencies that are called by threaded code to send things back
to the async event loop.
"""

from __future__ import annotations
from typing import Annotated
from fastapi import Depends, Request
from anyio.from_thread import BlockingPortal as RealBlockingPortal
from ..server import find_thing_server


def blocking_portal_from_thing_server(request: Request) -> RealBlockingPortal:
    """Return a UUID for an action invocation

    This is for use as a FastAPI dependency, to allow other dependencies to
    access the invocation ID. Useful for e.g. file management.
    """
    portal = find_thing_server(request.app).blocking_portal
    if portal is None:
        raise RuntimeError("Could not get the blocking portal from the server.")
    return portal


BlockingPortal = Annotated[
    RealBlockingPortal, Depends(blocking_portal_from_thing_server)
]
"""
A ready-made dependency type for a blocking portal. If you use an argument with
type `BlockingPortal`, FastAPI will automatically inject the blocking portal.
This is simply shorthand for {class}`anyio.from_thread.BlockingPortal` annotated with
`Depends(blocking_portal_from_thing_server)`.
"""
