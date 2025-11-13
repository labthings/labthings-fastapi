"""FastAPI dependencies for invocation-specific resources.

There are a number of LabThings-FastAPI features that are specific to each
invocation of an action.  These may be accessed using the :ref:`dependencies` in
this module.

It's important to understand how FastAPI handles dependencies when looking
at the code in this module. Each dependency (i.e. each callable passed as
the argument to `fastapi.Depends` in an annotated type) will be evaluated
only once per HTTP request. This means that we don't need to cache
`.InvocationID` and pass it between the functions, because the same ID
will be passed to every dependency that has an argument with the annotated
type `.InvocationID`.

When an action is invoked with a ``POST`` request, the endpoint function
responsible always has dependencies for the `.InvocationID` and
`.CancelHook`. These are added to the `.Invocation` thread that is created.
If the action declares dependencies with these types, it will receive the
same objects. This avoids the need for the action to be aware of its
`.Invocation`.

.. note::

    Currently, `.invocation_logger` is called from `.Invocation.run` with the
    invocation ID as an argument, and is not a direct dependency of the action's
    ``POST`` endpoint.

    This doesn't duplicate the returned logger object, as
    `logging.getLogger` may be called multiple
    times and will return the same `logging.Logger` object provided it is
    called with the same name.
"""

from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import Depends
import logging
from ..invocation_contexts import CancelEvent
from ..logs import THING_LOGGER


def invocation_id() -> uuid.UUID:
    """Generate a UUID for an action invocation.

    This is for use as a FastAPI dependency (see :ref:`dependencies`).

    Because `fastapi` only evaluates each dependency once per HTTP
    request, the `.UUID` we generate here is available to all of
    the dependencies declared by the ``POST`` endpoint that starts
    an action.

    Any dependency that has a parameter with the type hint
    `.InvocationID` will be supplied with the ID we generate
    here, it will be consistent within one HTTP request, and will
    be unique for each request (i.e. for each invocation of the
    action).

    This dependency is used by the `.InvocationLogger`, `.CancelHook`
    and other resources to ensure they all have the same ID, even
    before the `.Invocation` object has been created.

    :return: A unique ID for the current HTTP request, i.e. for this
        invocation of an action.
    """
    return uuid.uuid4()


InvocationID = Annotated[uuid.UUID, Depends(invocation_id)]
"""A FastAPI dependency that supplies the invocation ID.

This calls :func:`.invocation_id` to generate a new `.UUID`. It is used
to supply the invocation ID when an action is invoked.

Any dependency of an action may access the invocation ID by
using this dependency.
"""


def invocation_logger(id: InvocationID) -> logging.Logger:
    """Make a logger object for an action invocation.

    This function should be used as a dependency for an action, and
    will supply a logger that's specific to each invocation of that
    action. This is how `.Invocation.log` is generated.

    :param id: The Invocation ID, supplied as a FastAPI dependency.

    :return: A `logging.Logger` object specific to this invocation.
    """
    return THING_LOGGER.getChild("OLD_DEPENDENCY_LOGGER")


InvocationLogger = Annotated[logging.Logger, Depends(invocation_logger)]
"""A FastAPI dependency supplying a logger for the action invocation.

This calls `.invocation_logger` to generate a logger for the current
invocation. For details of how to use dependencies, see :ref:`dependencies`.
"""


def invocation_cancel_hook(id: InvocationID) -> CancelHook:
    """Make a cancel hook for a particular invocation.

    This is for use as a FastAPI dependency, and will create a
    `.CancelEvent` for use with a particular `.Invocation`.

    :param id: The invocation ID, supplied by FastAPI.

    :return: a `.CancelHook` event.
    """
    return CancelEvent(id)


CancelHook = Annotated[CancelEvent, Depends(invocation_cancel_hook)]
"""FastAPI dependency for an event that allows invocations to be cancelled.

This is an annotated type that returns a `.CancelEvent`, which can be used
to raise `.InvocationCancelledError` exceptions if the invocation is
cancelled, usually by a ``DELETE`` request to the invocation's URL.
"""
