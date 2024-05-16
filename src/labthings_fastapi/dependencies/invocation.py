"""FastAPI dependency for an invocation ID"""

from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import Depends
import logging
import threading


def invocation_id() -> uuid.UUID:
    """Return a UUID for an action invocation

    This is for use as a FastAPI dependency, to allow other dependencies to
    access the invocation ID. Useful for e.g. file management.
    """
    return uuid.uuid4()


InvocationID = Annotated[uuid.UUID, Depends(invocation_id)]


def invocation_logger(id: InvocationID) -> logging.Logger:
    """Retrieve a logger object for an action invocation

    This will have a level of at least INFO.
    """
    logger = logging.getLogger(f"labthings_fastapi.actions.{id}")
    logger.setLevel(logging.INFO)
    return logger


InvocationLogger = Annotated[logging.Logger, Depends(invocation_logger)]


class InvocationCancelledError(SystemExit):
    pass


class CancelEvent(threading.Event):
    def __init__(self, id: InvocationID):
        threading.Event.__init__(self)
        self.invocation_id = id

    def raise_if_set(self):
        """Raise a CancelledError if the event is set"""
        if self.is_set():
            raise InvocationCancelledError("The action was cancelled.")

    def sleep(self, timeout: float):
        """Sleep for a given time in seconds, but raise an exception if cancelled"""
        if self.wait(timeout):
            raise InvocationCancelledError("The action was cancelled.")


def invocation_cancel_hook(id: InvocationID) -> CancelHook:
    """Get a cancel hook belonging to a particular invocation"""
    return CancelEvent(id)


CancelHook = Annotated[CancelEvent, Depends(invocation_cancel_hook)]
