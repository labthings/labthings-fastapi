"""Handle pub-sub style events.

Both properties and actions can emit events that may be observed. This module handles
all the pub-sub messaging in LabThings.
"""

import anyio
from pydantic.dataclasses import dataclass
from typing import Any, Literal
from weakref import WeakSet

from anyio.abc import ObjectSendStream


@dataclass
class Message:
    """A pub-sub event message.

    This is the message that is sent when a property or action generates
    an event.

    This is a pydantic dataclass, so we validate the message. This might
    change in the future for performance reasons.

    :param thing: The name of the Thing generating the event.
    :param affordance: The name of the affordance generating the event.
    :param message: The message to send.
    """

    thing: str
    affordance: str
    message_type: Literal["property", "action", "event"]
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
            str, dict[str, WeakSet[ObjectSendStream[Message]]]
        ] = {}

    def subscribe(
        self, thing: str, affordance: str, stream: ObjectSendStream[Message]
    ) -> None:
        """Subscribe to messages from a particular affordance.

        Note that this method is not async - it just registers the stream and so
        can be run from any thread.

        :param thing: The name of the `.Thing` being subscribed to.
        :param affordance: The name of the affordance being subscribed to.
        :param stream: A stream to send the messages to.
        :raises TypeError: if the `thing` argument is not a string.
        """
        if not isinstance(thing, str):
            raise TypeError(f"The `thing` argument should be a string, not {thing}.")
        if thing not in self._subscriptions:
            self._subscriptions[thing] = {}
        if affordance not in self._subscriptions[thing]:
            self._subscriptions[thing][affordance] = WeakSet()
        self._subscriptions[thing][affordance].add(stream)

    def unsubscribe(
        self, thing: str, affordance: str, stream: ObjectSendStream[Message]
    ) -> None:
        """Unsubscribe a stream from messages from a particular affordance.

        :param thing: The name of the `.Thing` being unsubscribed from.
        :param affordance: The name of the affordance being unsubscribed from.
        :param stream: The stream to unsubscribe.
        :raises KeyError: if there is no such subscription.
        :raises TypeError: if the `thing` argument is not a string.
        """
        if not isinstance(thing, str):
            raise TypeError(f"The `thing` argument should be a string, not {thing}.")
        try:
            self._subscriptions[thing][affordance].discard(stream)
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
        for stream in subscriptions:
            await stream.send(message)

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
