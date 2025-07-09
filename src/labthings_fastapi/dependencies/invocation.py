"""FastAPI dependencies for invocation-specific resources.

There are a number of LabThings-FastAPI features that are specific to each
invocation of an action.  These may be accessed using the dependencies_ in
this module.
"""

from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import Depends
import logging
import threading


def invocation_id() -> uuid.UUID:
    """Generate a UUID for an action invocation.

    This is for use as a FastAPI dependency (see dependencies_).

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

This calls `.invocation_id` to generate a new `.UUID`. It is used
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
    logger = logging.getLogger(f"labthings_fastapi.actions.{id}")
    logger.setLevel(logging.INFO)
    return logger


InvocationLogger = Annotated[logging.Logger, Depends(invocation_logger)]
"""A FastAPI dependency supplying a logger for the action invocation.

This calls `.invocation_logger` to generate a logger for the current
invocation. For details of how to use dependencies, see dependencies_.
"""


class InvocationCancelledError(BaseException):
    """An invocation was cancelled by the user.

    Note that this inherits from BaseException so won't be caught by
    `except Exception`, it must be handled specifically.

    Action code may want to handle cancellation gracefully. This
    exception should be propagated if the action's status should be
    reported as ``cancelled``, or it may be handled so that the
    action finishes, returns a value, and is marked as ``completed``.

    If this exception is handled, the `.CancelEvent` should be reset
    to allow another `.InvocationCancelledError` to be raised if the
    invocation receives a second cancellation signal.
    """


class CancelEvent(threading.Event):
    """An Event subclass that enables cancellation of actions.

    This `threading.Event` subclass adds methods to raise
    `.InvocationCancelledError` exceptions if the invocation is cancelled,
    usually by a ``DELETE`` request to the invocation's URL.
    """

    def __init__(self, id: InvocationID):
        """Initialise the cancellation event.

        :param id: The invocation ID, annotated as a dependency so it is
            supplied automatically by FastAPI.
        """
        threading.Event.__init__(self)
        self.invocation_id = id

    def raise_if_set(self):
        """Raise a CancelledError if the event is set.

        :raises InvocationCancelledError: if the event has been cancelled.
        """
        if self.is_set():
            raise InvocationCancelledError("The action was cancelled.")

    def sleep(self, timeout: float):
        """Sleep for a given time in seconds, but raise an exception if cancelled.

        :raises InvocationCancelledError: if the event has been cancelled.
        """
        if self.wait(timeout):
            raise InvocationCancelledError("The action was cancelled.")


def invocation_cancel_hook(id: InvocationID) -> CancelHook:
    """Get a cancel hook belonging to a particular invocation"""
    return CancelEvent(id)


CancelHook = Annotated[CancelEvent, Depends(invocation_cancel_hook)]
