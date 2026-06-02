"""Test the message broker."""

import logging
from weakref import WeakSet

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


async def test_subscribe_unsubscribe():
    """Test that we can subscribe to affordances, and unsubscribe."""
    broker = MessageBroker()
    assert broker._subscriptions == {}

    send_stream, receive_stream = anyio.create_memory_object_stream[Message]()
    await broker.subscribe("thing_name", "prop", send_stream)

    assert send_stream in broker._subscriptions["thing_name"]["prop"]

    await broker.unsubscribe("thing_name", "prop", send_stream)
    assert send_stream not in broker._subscriptions["thing_name"]["prop"]

    # There's deliberately no validation when subscribing - that must come
    # from elsewhere. We do raise key errors for unsubscriptions though, if
    # there's no subscription to cancel.
    with pytest.raises(KeyError):
        await broker.unsubscribe("other_thing", "prop", send_stream)
    with pytest.raises(KeyError):
        await broker.unsubscribe("thing_name", "other_prop", send_stream)
    # There is currently no check that a subscription is current, so we don't
    # yet test if the stream is currently subscribed before deleting it from the
    # list of subscriptions. That means the following should work, even though
    # we're not currently subscribed:
    assert len(broker._subscriptions["thing_name"]["prop"]) == 0
    with pytest.raises(KeyError):
        await broker.unsubscribe("thing_name", "prop", send_stream)
    assert len(broker._subscriptions["thing_name"]["prop"]) == 0

    # We do check that the `thing` and `affordance` are strings, because it would
    # be very easy to pass a `Thing` by accident otherwise.
    with pytest.raises(TypeError):
        await broker.subscribe(Unjsonable(), "whatever", send_stream)  # type: ignore
    with pytest.raises(TypeError):
        await broker.unsubscribe(Unjsonable(), "whatever", send_stream)  # type: ignore
    with pytest.raises(TypeError):
        await broker.subscribe("whatever", Unjsonable(), send_stream)  # type: ignore
    with pytest.raises(TypeError):
        await broker.unsubscribe("whatever", Unjsonable(), send_stream)  # type: ignore


async def append_messages(
    stream: ObjectReceiveStream[Message],
    dest: list[Message],
):
    """Append messages from a stream to a list."""
    async with stream:
        async for item in stream:
            dest.append(item)


async def test_message_passing():
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

    async with anyio.create_task_group() as tg:
        # Set up the subscriptions
        retain_send_streams = []
        for thing, prop, dest in message_lists.values():
            # Subscribe to messages, and handle them by
            # appending to a list.
            # Note buffer size needs to be >0 or we'll drop messages
            # if they're sent before we start listening.
            send, recv = anyio.create_memory_object_stream[Message](5)
            await broker.subscribe(thing, prop, send)
            tg.start_soon(append_messages, recv, dest)
            # The line below stops the send stream getting garbage collected.
            retain_send_streams.append(send)
        # Now publish messages to the streams, then close them.
        tg.start_soon(publish_messages_and_shutdown)

    # Check that the messages were received by the expected streams
    assert message_lists["a_prop"][2] == [message_a]
    assert message_lists["c_prop"][2] == []
    assert message_lists["a_prop2"][2] == [message_a2] * 3
    assert message_lists["a_prop2_dup"][2] == [message_a2] * 3


async def test_close_streams():
    """Verify that close_streams actually closes the subscribed streams."""
    broker = MessageBroker()
    send_stream, receive_stream = anyio.create_memory_object_stream[Message]()

    # We subscribe to two affordances, to make sure it's not a problem to
    # close multiple subscriptions that are the same stream.
    await broker.subscribe("thing_a", "prop", send_stream)
    await broker.subscribe("thing_b", "prop", send_stream)
    await broker.close_streams()

    # Check the send stream was closed
    assert send_stream._closed is True

    # Check this propagates to the receive stream
    with pytest.raises(anyio.EndOfStream):
        await receive_stream.receive()


@pytest.mark.parametrize("action", ["close_send", "close_receive", "delete_send"])
async def test_sending_to_closed_streams(caplog, action):
    """Check that closing a stream causes it to unsubscribe."""
    caplog.set_level(logging.WARNING)
    broker = MessageBroker()
    send_stream, receive_stream = anyio.create_memory_object_stream[Message](2)
    await broker.subscribe("thing", "prop", send_stream)
    # Verify there's a subscription
    assert len(broker._subscriptions["thing"]["prop"]) == 1
    assert send_stream in broker._subscriptions["thing"]["prop"]
    message = Message("thing", "prop", "property", None)

    print("sending first message")
    # Check we can send and receive a message
    await broker.publish(message)
    received = await receive_stream.receive()
    assert received is message

    # Close or delete the stream
    if action == "close_send":
        await send_stream.aclose()
    elif action == "close_receive":
        await receive_stream.aclose()
    else:
        del send_stream  # streams are unsubscribed when they are finalised
    assert len(caplog.records) == 0
    print("sending second message")
    await broker.publish(message)
    assert len(caplog.records) == 0  # Shouldn't be any warnings in the log
    # Check we've been unsubscribed
    assert len(broker._subscriptions["thing"]["prop"]) == 0


async def test_sending_to_full_stream(caplog):
    """Check that a stream that's full logs a warning and doesn't block."""
    caplog.set_level(logging.WARNING)
    broker = MessageBroker()
    send_stream, receive_stream = anyio.create_memory_object_stream(max_buffer_size=1)
    await broker.subscribe("thing", "prop", send_stream)
    message = Message("thing", "prop", "property", None)

    # Check we can send and receive a message
    await broker.publish(message)
    received = await receive_stream.receive()
    assert received is message

    # Send another message, so the stream's buffer fills up
    await broker.publish(message)
    assert len(caplog.records) == 0

    # Send a third message, which should fail and log a warning
    await broker.publish(message)
    assert len(caplog.records) == 1
    msg = caplog.records[0].getMessage()
    assert msg.startswith("Could not pass notification to")
    assert msg.endswith("as it was full.")

    # Receive the message and clear the buffer
    received = await receive_stream.receive()
    assert received is message

    # Send and receive again - should be no further problems
    await broker.publish(message)
    received = await receive_stream.receive()
    assert received is message
    assert len(caplog.records) == 1


async def test_weakset_garbage_collection():
    """Check we can't cause a problem by garbage-collecting streams mid-send.

    This tests behaviour of Python and the garbage collector - it's not very clear to
    me from the Python docs when garbage collection may happen, or whether `WeakSet` is
    robust to it. This test checks I've understood that behaviour correctly, and should
    fail if Python's behaviour changes in a problematic way.

    The test iterates over a set of four objects, but deletes the strong references
    during the first iteration - if this were a regular set, it would cause an error.
    """
    items = {Unjsonable() for _ in range(4)}
    assert len(items) == 4
    weak = WeakSet(items)
    assert len(weak) == 4
    iterated = set()
    for item in weak:
        iterated.add(item)  # We don't know which item this will be
        del items  # There are now no references except to the one in `iterated`
    assert len(iterated) == 1  # We only iterated once, but there wasn't an error.
    # If we complete the test, it confirms we don't need to worry about streams being
    # finalized during iteration.
