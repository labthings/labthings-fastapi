r"""Handle notification of events, property, and action status changes via web sockets.

This module implements a websocket endpoint for a `.Thing`\ . It follows the
subprotocol set out at https://w3c.github.io/web-thing-protocol/ though compliance
with this protocol is not yet verified.

The W3C standard does not define a way for one websocket to handle
multiple Things, so for now the websocket endpoint will be associated
with a single Thing instance. This may change in the future.

(c) Richard Bowman July 2023, released under MIT license
"""

from __future__ import annotations
from anyio import create_memory_object_stream, create_task_group
from anyio.abc import ObjectReceiveStream, ObjectSendStream
import logging
from fastapi import WebSocket, WebSocketDisconnect
from typing import TYPE_CHECKING, Literal

from labthings_fastapi.middleware.url_for import URLFor
from .exceptions import PropertyNotObservableError
from .events import Message
from . import webthing_subprotocol

if TYPE_CHECKING:
    from .thing import Thing


WEBTHING_ERROR_URL = "https://w3c.github.io/web-thing-protocol/errors"


def observation_error_response(
    thing: Thing,
    affordance: str,
    affordance_type: Literal["action", "property"],
    exception: Exception,
) -> webthing_subprotocol.ObservationErrorResponse:
    r"""Generate a websocket error response for observing an action or property.

    When a websocket client asks to observe a property or action that either
    doesn't exist or isn't observable, this function makes a dictionary that
    can be returned to the client indicating an error.

    :param name: The name of the affordance being observed.
    :param affordance_type: The type of the affordance.
    :param exception: The error that was raised.
    :returns: A dictionary that may be returned to the websocket.

    :raises TypeError: if the exception is not a `KeyError`
        or `.PropertyNotObservableError`\ .
    """
    if isinstance(exception, KeyError):
        error = webthing_subprotocol.ProblemDetails(
            status=404,
            type=f"{WEBTHING_ERROR_URL}#not-found",
            title="Not Found",
            detail=f"No {affordance_type} found with the name '{affordance}'.",
        )
    elif isinstance(exception, PropertyNotObservableError):
        error = webthing_subprotocol.ProblemDetails(
            status=403,
            type=f"{WEBTHING_ERROR_URL}#not-observable",
            title="Not Observable",
            detail=f"Property '{affordance}' is not observable.",
        )
    else:
        raise TypeError(f"Can't generate an error response for {exception}.")
    return webthing_subprotocol.ObservationErrorResponse(
        thingID=URLFor(f"things.{thing.name}"),
        messageType="response",
        operation="observeaction" if affordance_type == "action" else "observeproperty",
        name=affordance,
        error=error,
    )


NOTIFICATION_MODELS = {
    "property": webthing_subprotocol.ObservePropertyNotification,
    "action": webthing_subprotocol.ObserveActionNotification,
    "event": webthing_subprotocol.ObserveEventNotification,
}


async def relay_notifications_to_websocket(
    websocket: WebSocket, receive_stream: ObjectReceiveStream[Message]
) -> None:
    """Relay objects from a stream to a websocket as JSON.

    :ref:`wot_affordances` (events, actions) that we've registered with will
    post messages to the queue: this function takes those messages from the
    queue and passes them to the websocket.

    :param websocket: the WebSocket we are communicating over.
    :param receive_stream: an `anyio.abc.ObjectReceiveStream` that will
        yield objects that we send over the websocket.
    """
    async with receive_stream:
        async for item in receive_stream:
            await websocket.send_text(item.model_dump_json())


async def process_messages_from_websocket(
    websocket: WebSocket, send_stream: ObjectSendStream[Message], thing: Thing
) -> None:
    r"""Process messages received from a websocket.

    Currently, this will allow us to observe properties, by registering
    (or de-registering) for those properties.

    :param websocket: the WebSocket we are communicating over.
    :param send_stream: an `anyio.abc.ObjectSendStream` that we
        use to register for events, i.e. data sent to that stream will
        be sent through this websocket, by `.relay_notifications_to_websocket`\ .
    :param thing: the `.Thing` we are attached to. The websocket is specific to
        one `.Thing`, and this is it.
    """
    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            await send_stream.aclose()
            return
        if data["messageType"] == "request" and data["operation"] == "observeproperty":
            try:
                k = data.get("name", default="")  # The empty string will raise KeyError
                thing.properties[k].observe(send_stream)
            except (KeyError, PropertyNotObservableError) as e:
                logging.error(f"Got a bad websocket message: {data}, caused {e!r}.")
                await send_stream.send(observation_error_response(k, "property", e))
        if data["messageType"] == "request" and data["operation"] == "observeaction":
            try:
                k = data.get("name", default="")  # The empty string will raise KeyError
                thing.actions[k].observe(send_stream)
            except KeyError as e:
                logging.error(f"Got a bad websocket message: {data}, caused {e!r}.")
                await send_stream.send(observation_error_response(k, "action", e))
        else:
            logging.error(f"Got an unknown websocket message: {data}.")
            # Close the stream rather than ignoring bad messages. This will
            # cause the websocket client to error out rather than hanging.
            await send_stream.aclose()
            return


async def websocket_endpoint(thing: Thing, websocket: WebSocket) -> None:
    r"""Handle communication to a client via websocket.

    This function handles a websocket connection to a `.Thing`\ 's websocket
    endpoint. It can add observers to properties and actions, and will forward
    notifications from the property or action back to the websocket.

    :param thing: the `.Thing` the websocket is attached to.
    :param websocket: the web socket that has been created.
    """
    await websocket.accept()
    send_stream, receive_stream = create_memory_object_stream[Message]()
    async with create_task_group() as tg:
        tg.start_soon(relay_notifications_to_websocket, websocket, receive_stream)
        tg.start_soon(process_messages_from_websocket, websocket, send_stream, thing)
