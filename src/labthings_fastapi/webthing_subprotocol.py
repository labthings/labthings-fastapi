"""WebThing WebSocket subprotocol models.

This module defines models for the messages sent over websockets, which are aligned with
the ``webthingprotocol`` subprotocol as set out in the `community group draft report`_.

.. _community group draft report: https://w3c.github.io/web-thing-protocol/

(c) Richard Bowman July 2023, released under MIT license
"""

from datetime import datetime
from uuid import uuid4, UUID
from typing import Any, Literal
from pydantic import BaseModel, Field

from labthings_fastapi.middleware.url_for import URLFor


class WebsocketMessage(BaseModel):
    """A base model for all websocket messages."""

    thingID: str | URLFor
    messageID: UUID = Field(default_factory=uuid4)
    messageType: Literal["request", "response", "notification"]
    operation: str
    correlationID: UUID | None = None


class ObservePropertyMessage(WebsocketMessage):
    """A base model for messages related to observing a property."""

    name: str
    operation: Literal["observeproperty"] = "observeproperty"


class ObservePropertyNotification(ObservePropertyMessage):
    """A model for property change messages."""

    messageType: Literal["notification"] = "notification"
    value: Any


class ObserveActionMessage(WebsocketMessage):
    """A base model for messages related to observing an action."""

    name: str
    operation: Literal["observeaction"] = "observeaction"


class ObserveActionNotification(ObserveActionMessage):
    """A model for action notification messages.

    This is not part of the webthingprotocol draft, so should be considered
    at risk of summary removal.
    """

    messageType: Literal["notification"] = "notification"
    actionID: UUID
    state: Literal["pending", "running", "completed", "failed"]


class ActionStatus(BaseModel):
    """The status of an action invocation."""

    actionID: UUID
    state: Literal["pending", "running", "completed", "failed"]
    output: Any | None = None
    error: "ProblemDetails | None" = None
    timeRequested: datetime | None = None
    timeEnded: datetime | None = None


class ProblemDetails(BaseModel):
    """Details of an error.

    This follows RFC9457_.

    .. _RFC9457: https://datatracker.ietf.org/doc/html/rfc9457
    """

    status: int
    type: str
    title: str
    detail: str | None = None


class ObservationErrorResponse(WebsocketMessage):
    """A websocket error response for observing an action or property."""

    messageType: Literal["response"] = "response"
    operation: Literal["observeaction", "observeproperty"]
    name: str
    error: ProblemDetails
