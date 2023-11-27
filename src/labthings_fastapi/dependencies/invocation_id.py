"""FastAPI dependency for an invocation ID"""
from __future__ import annotations
import uuid
from typing import Annotated
from fastapi import Depends


def invocation_id() -> uuid.UUID:
    """Return a UUID for an action invocation

    This is for use as a FastAPI dependency, to allow other dependencies to
    access the invocation ID. Useful for e.g. file management.
    """
    return uuid.uuid4()


InvocationID = Annotated[uuid.UUID, Depends(invocation_id)]
