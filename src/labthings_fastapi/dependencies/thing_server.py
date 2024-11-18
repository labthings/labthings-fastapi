"""
Retrieve the ThingServer object

This module provides a function that will retrieve the ThingServer
based on the `Request` object. It may be used as a dependency with:
`Annotated[ThingServer, Depends(thing_server_from_request)]`.
"""

from __future__ import annotations
from weakref import WeakSet
from typing import TYPE_CHECKING
from fastapi import FastAPI, Request

if TYPE_CHECKING:
    from labthings_fastapi.server import ThingServer

_thing_servers: WeakSet[ThingServer] = WeakSet()


def find_thing_server(app: FastAPI) -> ThingServer:
    """Find the ThingServer associated with an app"""
    for server in _thing_servers:
        if server.app == app:
            return server
    raise RuntimeError("No ThingServer found for this app")


def thing_server_from_request(request: Request) -> ThingServer:
    """Retrieve the Action Manager from the Thing Server

    This is for use as a FastAPI dependency, so the thing server is
    retrieved from the request object.
    """
    return find_thing_server(request.app)
