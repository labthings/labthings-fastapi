"""Invocation Model.

This module contains types used to describe an `.Invocation`.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
import logging
from typing import Optional, Any, Sequence, TypeVar, Generic
import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from ..thing_description.model import Links


class InvocationStatus(Enum):
    """The current status of an `.Invocation`."""

    PENDING = "pending"
    """The `.Invocation` has not yet been started."""
    RUNNING = "running"
    """The `.Invocation` is running in its thread."""
    COMPLETED = "completed"
    """The `.Invocation` finished successfully. A return value may be available."""
    CANCELLED = "cancelled"
    """The `.Invocation` was cancelled and has finished."""
    ERROR = "error"
    """The `.Invocation` terminated unexpectedly due to an error."""


class LogRecordModel(BaseModel):
    """A model to serialise `logging.LogRecord` objects."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    message: str
    levelname: str
    levelno: int
    lineno: int
    filename: str
    created: datetime

    @model_validator(mode="before")
    @classmethod
    def generate_message(cls, data: Any) -> Any:
        """Ensure LogRecord objects have constructed their message.
        
        :param data: The LogRecord to process.
        
        :return: The LogRecord, with a message constructed.
        """
        if not hasattr(data, "message"):
            if isinstance(data, logging.LogRecord):
                try:
                    data.message = data.getMessage()
                except (ValueError, TypeError) as e:
                    # too many args causes an error - but errors
                    # in validation can be a problem for us:
                    # it will cause 500 errors when retrieving
                    # the invocation.
                    # This way, you can find and fix the source.
                    data.message = f"Error constructing message ({e}) from {data!r}."
        return data


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class GenericInvocationModel(BaseModel, Generic[InputT, OutputT]):
    """A model to serialise `.Invocation` objects when they are polled over HTTP.

    The input and output models are generic parameters, to allow this model to
    be used for specific Actions. These are usually set to `Any` because the
    invocation endpoint is not specific to any one Action, and thus the types
    are not known in advance.
    """

    status: InvocationStatus
    id: uuid.UUID
    action: str
    href: str
    timeStarted: Optional[datetime]
    timeRequested: Optional[datetime]
    timeCompleted: Optional[datetime]
    input: InputT
    output: OutputT
    log: Sequence[LogRecordModel]
    links: Links = None


InvocationModel = GenericInvocationModel[Any, Any]
