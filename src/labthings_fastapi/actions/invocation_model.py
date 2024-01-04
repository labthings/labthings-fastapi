from __future__ import annotations
from datetime import datetime
from enum import Enum
import logging
from typing import Optional, Any, Sequence, TypeVar, Generic
import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from labthings_fastapi.thing_description.model import Links


class InvocationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class LogRecordModel(BaseModel):
    """A model to serialise logging.LogRecord objects"""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    message: str
    levelname: str
    levelno: int
    lineno: int
    filename: str
    created: datetime

    @model_validator(mode="before")
    @classmethod
    def generate_message(cls, data: Any):
        if not hasattr(data, "message"):
            if isinstance(data, logging.LogRecord):
                data.message = data.getMessage()
        return data


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class GenericInvocationModel(BaseModel, Generic[InputT, OutputT]):
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
