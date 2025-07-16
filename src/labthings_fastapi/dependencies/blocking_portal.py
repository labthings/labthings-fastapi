"""FastAPI dependency for a blocking portal.

This allows dependencies that are called by threaded code to send things back
to the async event loop. See :ref:`concurrency` for more details.

Threaded code can call asynchronous code in the `anyio` event loop used by
`fastapi`, if an `anyio.BlockingPortal` is used.

The `.ThingServer` sets up an `anyio.from_thread.BlockingPortal` when the server starts
(in `.ThingServer.lifespan`). This may be accessed from an action using the
`.BlockingPortal` dependency in this module.

.. note::

    The blocking portal is accessed via a dependency to ensure we only ever
    use the blocking portal attached to the server handling the current
    request.

    This may be simplified in the future, as a `.Thing` can only ever be
    attached to one `.ThingServer`, and each `.ThingServer` corresponds
    to exactly one event loop. That means a mechanism may be introduced in
    the future that allows `.Thing` code to access a blocking portal without
    the need for a dependency.
"""

from __future__ import annotations
from typing import Annotated
from fastapi import Depends, Request
from anyio.from_thread import BlockingPortal as RealBlockingPortal
from .thing_server import find_thing_server


def blocking_portal_from_thing_server(request: Request) -> RealBlockingPortal:
    r"""Return the blocking portal from our ThingServer.

    This is for use as a FastAPI dependency, to allow threaded code to call
    async code. See the module-level docstring for `.blocking_portal`.

    :param request: The `fastapi.Request` object, supplied by the :ref:`dependencies`
        mechanism.

    :return: the `anyio.from_thread.BlockingPortal` allowing access to te
        `.ThingServer`\ 's event loop.
    """
    portal = find_thing_server(request.app).blocking_portal
    assert portal is not None, RuntimeError(
        "Could not get the blocking portal from the server."
        # This should never happen, as the blocking portal is added
        # and removed in `.ThingServer.lifecycle`.
    )
    return portal


BlockingPortal = Annotated[
    RealBlockingPortal, Depends(blocking_portal_from_thing_server)
]
"""
A ready-made dependency type for a blocking portal. If you use an argument with
type `.BlockingPortal`, FastAPI will automatically inject the blocking portal.
This is simply shorthand for `anyio.from_thread.BlockingPortal` annotated with
``Depends(blocking_portal_from_thing_server)``.
"""
