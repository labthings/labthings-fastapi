from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional, Any, TypeVar, Generic
import uuid

from pydantic import BaseModel

from labthings_fastapi.thing_description.model import Links

class InvocationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


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
    links: Links = None

InvocationModel = GenericInvocationModel[Any, Any]