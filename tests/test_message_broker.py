"""Test the message broker."""

import anyio
from anyio.abc import ObjectReceiveStream
import pytest

from pydantic import ValidationError

from labthings_fastapi.message_broker import Message, MessageBroker


class Unjsonable:
    """A class that won't serialise."""


@pytest.mark.parametrize(
    "message",
    [
        ("test_thing", "prop", "property", 42),
        ("test_thing", "prop", "property", Unjsonable()),
        ("test_thing", "do_it", "action", None),
        ("test_thing", "notify", "action", {"key": "value"}),
    ],
)
def test_message_valid(message):
    """Check that Messages can be constructed."""
    amodel = Message(*message)
    ARGS = ["thing", "affordance", "message_type", "payload"]
    kwargs = dict(zip(ARGS, message, strict=True))
    kmodel = Message(**kwargs)
    assert amodel == kmodel
    assert amodel.__dict__ == kwargs


@pytest.mark.parametrize(
    "message",
    [
        ("test_thing", "prop", "custom", None),
        (Unjsonable(), "prop", "property", None),
        ("thing", Unjsonable(), "property", None),
    ],
)
def test_message_invalid(message):
    """Check that invalid Things or message types fail validation."""
    with pytest.raises(ValidationError):
        _ = Message(*message)


def test_subscribe_unsubscribe():
    """Test that we can subscribe to affordances, and unsubscribe."""
    broker = MessageBroker()
    assert broker._subscriptions == {}

    send_stream, receive_stream = anyio.create_memory_object_stream[Message]()
    broker.subscribe("thing_name", "prop", send_stream)

    assert send_stream in broker._subscriptions["thing_name"]["prop"]

    broker.unsubscribe("thing_name", "prop", send_stream)
    assert send_stream not in broker._subscriptions["thing_name"]["prop"]

    # There's deliberately no validation when subscribing - that must come
    # from elsewhere. We do raise key errors for unsubscriptions though, if
    # there's no subscription to cancel.
    with pytest.raises(KeyError):
        broker.unsubscribe("other_thing", "prop", send_stream)
    with pytest.raises(KeyError):
        broker.unsubscribe("thing_name", "other_prop", send_stream)
    # There is currently no check that a subscription is current, so we don't
    # yet test if the stream is currently subscribed before deleting it from the
    # list of subscriptions. That means the following should work, even though
    # we're not currently subscribed:
    assert len(broker._subscriptions["thing_name"]["prop"]) == 0
    broker.unsubscribe("thing_name", "prop", send_stream)
    assert len(broker._subscriptions["thing_name"]["prop"]) == 0

    # We do check that the `thing` and `affordance` are strings, because it would
    # be very easy to pass a `Thing` by accident otherwise.
    with pytest.raises(TypeError):
        broker.subscribe(Unjsonable(), "whatever", send_stream)  # type: ignore
    with pytest.raises(TypeError):
        broker.unsubscribe(Unjsonable(), "whatever", send_stream)  # type: ignore
    with pytest.raises(TypeError):
        broker.subscribe("whatever", Unjsonable(), send_stream)  # type: ignore
    with pytest.raises(TypeError):
        broker.unsubscribe("whatever", Unjsonable(), send_stream)  # type: ignore


async def append_messages(
    stream: ObjectReceiveStream[Message],
    dest: list[Message],
):
    """Append messages from a stream to a list."""
    async with stream:
        async for item in stream:
            dest.append(item)


def test_message_passing():
    """Check messages propagate in an event loop.

    We test messages with 0, 1, and 2 subscribers.
    """
    message_a = Message("thing_a", "prop", "property", "a")
    message_b = Message("thing_b", "prop", "property", "b")
    message_a2 = Message("thing_a", "prop2", "property", "a2")

    broker = MessageBroker()

    async def publish_messages_and_shutdown():
        """Publish several messages."""
        await broker.publish(message_a)
        await broker.publish(message_b)  # not received - but no error either
        await broker.publish(message_a2)
        await broker.publish(message_a2)
        await broker.publish(message_a2)
        # It's important to close streams or the test hangs.
        await broker.close_streams()

    # We make four subscriptions, defined below.
    # Each has a thing name and property name. Any messages received will be
    # appended to the list.
    message_lists = {
        "a_prop": ("thing_a", "prop", []),  # message_a
        "c_prop": ("thing_c", "prop", []),  # no message
        "a_prop2": ("thing_a", "prop2", []),  # message_a3 x3
        "a_prop2_dup": ("thing_a", "prop2", []),  # as above
    }

    # Define the async code that runs in an event loop
    async def main():
        async with anyio.create_task_group() as tg:
            retain_send_streams = []
            for thing, prop, dest in message_lists.values():
                # Subscribe to messages, and handle them by
                # appending to a list.
                send, recv = anyio.create_memory_object_stream[Message]()
                broker.subscribe(thing, prop, send)
                tg.start_soon(append_messages, recv, dest)
                # The line below stops the send stream getting garbage collected.
                retain_send_streams.append(send)
            tg.start_soon(publish_messages_and_shutdown)

    # Run the function in an event loop
    anyio.run(main)

    # Check that the messages were received by the expected streams
    assert message_lists["a_prop"][2] == [message_a]
    assert message_lists["c_prop"][2] == []
    assert message_lists["a_prop2"][2] == [message_a2] * 3
    assert message_lists["a_prop2_dup"][2] == [message_a2] * 3


if __name__ == "__main__":
    test_message_passing()
