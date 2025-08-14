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
import threading


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
    logger = logging.getLogger(f"labthings_fastapi.actions.{id}")
    logger.setLevel(logging.INFO)
    return logger


InvocationLogger = Annotated[logging.Logger, Depends(invocation_logger)]
"""A FastAPI dependency supplying a logger for the action invocation.

This calls `.invocation_logger` to generate a logger for the current
invocation. For details of how to use dependencies, see :ref:`dependencies`.
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


class InvocationError(RuntimeError):
    """The invocation ended in an anticipated error state.

    When this error is raised, action execution stops as expected. The exception will be
    logged at error level without a traceback, and the invocation will return with
    error status.

    Subclass this error for errors that do not need further traceback information
    to be provided with the error message in logs.
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

    def raise_if_set(self) -> None:
        """Raise an exception if the event is set.

        This is intended as a compact alternative to:

        .. code-block::

            if cancel_event.is_set():
                raise InvocationCancelledError()

        :raise InvocationCancelledError: if the event has been cancelled.
        """
        if self.is_set():
            raise InvocationCancelledError("The action was cancelled.")

    def sleep(self, timeout: float) -> None:
        r"""Sleep for a given time in seconds, but raise an exception if cancelled.

        This function can be used in place of `time.sleep`. It will usually behave
        the same as `time.sleep`\ , but if the cancel event is set during the time
        when we are sleeping, an exception is raised to interrupt the sleep and
        cancel the action.

        :param timeout: The time to sleep for, in seconds.

        :raise InvocationCancelledError: if the event has been cancelled.
        """
        if self.wait(timeout):
            raise InvocationCancelledError("The action was cancelled.")


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
