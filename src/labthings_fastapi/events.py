"""Handle pub-sub style events.

Both properties and actions can emit events that may be observed. This module handles
all the pub-sub messaging in LabThings.

This module defines models for the messages sent over websockets, which are aligned with
the ``webthingprotocol`` subprotocol as set out in the `community group draft report`_.

.. _community group draft report: https://w3c.github.io/web-thing-protocol/
"""

from dataclasses import dataclass
from typing import Any, Literal
from weakref import WeakSet

from anyio.abc import ObjectSendStream


@dataclass
class Message:
    """A pub-sub event message.

    This is the message that is sent when a property or action generates
    an event.

    :param thing: The name of the Thing generating the event.
    :param affordance: The name of the affordance generating the event.
    :param message: The message to send.
    """

    thing: str
    affordance: str
    message_type: Literal["property", "action", "event"]
    payload: Any


class MessageBroker:
    """A class that relays pub/sub messages."""

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
        """
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
        """
        try:
            self._subscriptions[thing][affordance].discard(stream)
        except KeyError as e:
            raise e

    async def publish(self, message: Message) -> None:
        """Publish a message.

        :param thing: the name of the `.Thing` we are publishing about.
        :param affordance: the name of the affordance generating the message.
        :param message: the message to send.
        """
        try:
            subscriptions = self._subscriptions[message.thing][message.affordance]
        except KeyError:
            return  # No subscribers for this thing.
        for stream in subscriptions:
            await stream.send(message)
