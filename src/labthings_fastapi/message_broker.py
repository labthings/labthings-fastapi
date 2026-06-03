"""Handle pub-sub style events.

Both properties and actions can emit events that may be observed. This module handles
all the pub-sub messaging in LabThings.
"""

import anyio
from pydantic.dataclasses import dataclass
from typing import Any, Literal
from weakref import WeakSet
import logging
import warnings

from anyio.streams.memory import MemoryObjectSendStream

from labthings_fastapi.exceptions import MessageDroppedWarning


LOGGER = logging.getLogger(__name__)


@dataclass
class Message:
    """A pub-sub event message.

    This is the message that is sent when a property or action generates
    an event.

    This is a pydantic dataclass, so we validate the message. This might
    change in the future for performance reasons.

    :param thing: The name of the Thing generating the event.
    :param affordance: The name of the affordance generating the event.
    :param message_type: The kind of affordance from which the event originates.
    :param payload: Data specific to the event (e.g. property value, action status).
    """

    thing: str
    affordance: str
    message_type: Literal["property", "action"]
    payload: Any


class MessageBroker:
    r"""A class that relays pub/sub messages.

    This class takes care of relaying messages to streams that have subscribed to them.
    It does not format messages or handle any details of e.g. websocket protocol.

    Subscriptions require an `ObjectSendStream[Message]` and each time a `Message`
    matching the subscription parameters (``thing`` and ``affordance``) is published,
    it will be sent on that stream.

    The broker does not validate thing or affordance names: that's up to the code
    calling `MessageBroker.subscribe`\ .
    """

    def __init__(self) -> None:
        """Initialise the message broker."""
        # Note that we use a weak set below, so that when a websocket disconnects,
        # its stream is removed automatically.
        self._subscriptions: dict[
            str, dict[str, WeakSet[MemoryObjectSendStream[Message]]]
        ] = {}

    async def subscribe(
        self, thing: str, affordance: str, stream: MemoryObjectSendStream[Message]
    ) -> None:
        """Subscribe to messages from a particular affordance.

        Note that this method must be called from the event loop, as the message
        broker is deliberately not thread safe.

        :param thing: The name of the `.Thing` being subscribed to.
        :param affordance: The name of the affordance being subscribed to.
        :param stream: A stream to send the messages to.
        :raises TypeError: if the `thing` or `affordance` argument is not a string.
        """
        if not isinstance(thing, str):
            raise TypeError(f"`thing` must be a string, not '{thing}'.")
        if not isinstance(affordance, str):
            raise TypeError(f"`affordance` must be a string, not '{affordance}'.")
        affordances = self._subscriptions.setdefault(thing, {})
        streams = affordances.setdefault(affordance, WeakSet())
        streams.add(stream)

    async def unsubscribe(
        self, thing: str, affordance: str, stream: MemoryObjectSendStream[Message]
    ) -> None:
        """Unsubscribe a stream from messages from a particular affordance.

        This function is often not necessary: streams will be unsubscribed automatically
        if they are closed or finalised. As the message broker only keeps a weak
        reference to the stream, that means it will be finalized and unsubscribed
        when the code that created it goes out of scope.

        :param thing: The name of the `.Thing` being unsubscribed from.
        :param affordance: The name of the affordance being unsubscribed from.
        :param stream: The stream to unsubscribe.
        :raises KeyError: if there is no such subscription.
        :raises TypeError: if the `thing` or `affordance` argument is not a string.
        """
        if not isinstance(thing, str):
            raise TypeError(f"`thing` must be a string, not '{thing}'.")
        if not isinstance(affordance, str):
            raise TypeError("`affordance` must be a string, not '{affordance}'.")
        try:
            self._subscriptions[thing][affordance].remove(stream)
        except KeyError as e:
            raise e

    async def publish(self, message: Message) -> None:
        """Publish a message.

        This async method will relay the message to any subscriber streams.

        :param message: the message to send.
        """
        try:
            subscriptions = self._subscriptions[message.thing][message.affordance]
        except KeyError:
            return  # No subscribers for this thing.
        subscriptions_to_remove = set()
        for stream in subscriptions:
            try:
                stream.send_nowait(message)
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                # Streams that have been closed will be automatically unsubscribed.
                # They can't be reopened, so they won't be reused.
                subscriptions_to_remove.add(stream)
            except anyio.WouldBlock:
                msg = f"Could not pass notification to {stream} as it was full."
                LOGGER.warning(msg)
                warnings.warn(MessageDroppedWarning(msg), stacklevel=1)
        for stream in subscriptions_to_remove:
            # discard rather than remove, so that if the stream has been finalized
            # since it was closed, we don't get an error.
            subscriptions.discard(stream)

    async def close_streams(self) -> None:
        """Close all streams that are subscribed to receive messages.

        This should be called when the server shuts down.
        """
        # We use a task group so we shut down all streams concurrently, rather
        # than waiting for each one to close.
        async with anyio.create_task_group() as tg:
            for thing_subs in self._subscriptions.values():
                for subs in thing_subs.values():
                    for stream in subs:
                        tg.start_soon(stream.aclose)
