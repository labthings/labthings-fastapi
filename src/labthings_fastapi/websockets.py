"""
Handle notification of events, property, and action status changes

There are several kinds of "event" in the WoT vocabulary, not all of which
are called Event, which is why this module is called `notifications`.
In all cases, these are events that happen on an exposed Thing, and
may need to be relayed to one or more listeners (currently via a
WebSocket connection, though long polling may also be an option in the
future).

The aim at this stage (July 2023) is for a minimal working example that
enables property changes to be fed via a websocket. Events proper should
not be a big step thereafter.

The W3C standard does not define a way for one websocket to handle
multiple Things, so for now the websocket endpoint will be associated
with a single Thing instance. This may change in the future.

(c) Richard Bowman July 2023, released under GNU-LGPL-3.0
"""

from __future__ import annotations
from anyio import create_memory_object_stream, create_task_group
from anyio.abc import ObjectReceiveStream, ObjectSendStream
import logging
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .thing import Thing


async def relay_notifications_to_websocket(
    websocket: WebSocket, receive_stream: ObjectReceiveStream
) -> None:
    """Relay objects from a stream to a websocket as JSON

    Interaction affordances (events, actions) that we've registered with will
    post messages to the queue: this function takes those messages from the
    queue and passes them to the websocket.
    """
    async with receive_stream:
        async for item in receive_stream:
            await websocket.send_json(jsonable_encoder(item))


async def process_messages_from_websocket(
    websocket: WebSocket, send_stream: ObjectSendStream, thing: Thing
) -> None:
    """Process messages received from a websocket

    Currently, this will allow us to observe properties, by registering
    (or de-registering) for those properties.
    """
    while True:
        try:
            data = await websocket.receive_json()
            if data["messageType"] == "addPropertyObservation":
                for k in data["data"].keys():
                    thing.observe_property(k, send_stream)
            if data["messageType"] == "addActionObservation":
                for k in data["data"].keys():
                    thing.observe_action(k, send_stream)
        except KeyError as e:
            logging.error(f"Got a bad websocket message: {data}, caused KeyError({e})")
        except WebSocketDisconnect:
            await send_stream.aclose()
            return


async def websocket_endpoint(thing: Thing, websocket: WebSocket) -> None:
    """Handle communication to a client via websocket"""
    await websocket.accept()
    send_stream, receive_stream = create_memory_object_stream[dict]()
    async with create_task_group() as tg:
        tg.start_soon(relay_notifications_to_websocket, websocket, receive_stream)
        tg.start_soon(process_messages_from_websocket, websocket, send_stream, thing)
