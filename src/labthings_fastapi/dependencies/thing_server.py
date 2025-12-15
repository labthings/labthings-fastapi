"""Retrieve the `.ThingServer` object.

This module provides a function that will retrieve the `.ThingServer`
based on the `fastapi.Request` object. It may be used as a dependency with
``Annotated[ThingServer, Depends(thing_server_from_request)]``.

See :ref:`dependencies` for more information on the dependency mechanism,
and :ref:`things_from_things` for more on how `.Things` interact.

.. note::

    This module does not provide a ready-made annotated type to use as a
    dependency. Doing so would mean this module has a hard dependency on
    `.ThingServer` and cause circular references. See above for the
    annotated type, which you may define in any code that needs it.

.. note::

    The rationale for this function is that we want to make sure `.Thing`
    instances only access the server associated with the current request.
    This means that we use the `fastapi.Request` to look up the
    `fastapi.FastAPI` app, and then use the app to look up the `.ThingServer`.

    As each `.Thing` is connected to exactly one `.ThingServer`, this may
    become unnecessary in the future as the server could be exposed as a
    property of the `.Thing`.
"""

from __future__ import annotations
from weakref import WeakSet
from typing import TYPE_CHECKING
from warnings import warn
from fastapi import FastAPI, Request

if TYPE_CHECKING:
    from ..server import ThingServer

_thing_servers: WeakSet[ThingServer] = WeakSet()


def find_thing_server(app: FastAPI) -> ThingServer:
    """Find the ThingServer associated with an app.

    This function will return the `.ThingServer` object that contains
    a particular `fastapi.FastAPI` app. The app is available as part
    of the `fastapi.Request` object, so this makes it possible to
    get the `.ThingServer` in dependency functions.

    This function will not work as a dependency, but
    `.thing_server_from_request` will.

    :param app: The `fastapi.FastAPI` application that implements the
        `.ThingServer`, i.e. this is ``thing_server.app``.

    :return: the `.ThingServer` that owns the ``app``.

    :raise RuntimeError: if there is no `.ThingServer` associated
        with the current FastAPI application. This should only happen
        if this function is called on a `fastapi.FastAPI` instance
        that was not created by a `.ThingServer`.
    """
    warn(
        "`find_thing_server` and `thing_server_from_request` are deprecated "
        "and will be removed in v0.1.0. Use `Thing.thing_server_interface` "
        "instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    for server in _thing_servers:
        if server.app == app:
            return server
    raise RuntimeError("No ThingServer found for this app")


def thing_server_from_request(request: Request) -> ThingServer:
    """Retrieve the `.ThingServer` from a request.

    This is for use as a FastAPI dependency, so the thing server is
    retrieved from the request object. See `.find_thing_server`.

    It may be used as a dependency with:

    .. code-block:: python

        ServerDep = Annotated[ThingServer, Depends(thing_server_from_request)]

    This is not provided as a ready-made annotated type because it would
    introduce a hard dependency on the :mod:`.server` module and cause circular
    references.

    :param request: is supplied automatically by FastAPI when used
        as a dependency.

    :return: the `.ThingServer` handling the current request.
    """
    return find_thing_server(request.app)
