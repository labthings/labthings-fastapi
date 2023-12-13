from typing import Annotated
from .invocation_id import InvocationID
import logging
from fastapi import Depends


def invocation_logger(id: InvocationID) -> logging.Logger:
    """Retrieve a logger object for an action invocation"""
    return logging.getLogger(f"labthings_fastapi.actions.{id}")


InvocationLogger = Annotated[logging.Logger, Depends(invocation_logger)]
