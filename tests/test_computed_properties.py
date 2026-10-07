"""Test computed properties in isolation."""

from typing import Literal

import anyio
import pytest
from anyio.to_thread import run_sync
from httpx2 import ASGITransport, AsyncClient

import labthings_fastapi as lt
from labthings_fastapi.computed_properties import computed_property
from labthings_fastapi.exceptions import PropertyNotObservableError
from labthings_fastapi.message_broker import Message
from labthings_fastapi.testing import create_thing_without_server


class MyThing(lt.Thing):
    quantity: int = lt.property(default=0)
    quantity2: int = lt.property(default=0)
    selector: Literal["q1", "q2"] = lt.property(default="q1")

    @computed_property
    def double(self) -> int:
        return 2 * self.quantity

    @computed_property
    def selected(self) -> int:
        if self.selector == "q1":
            return self.quantity
        elif self.selector == "q2":
            return self.quantity2
        else:
            raise ValueError("invalid selector")

    @lt.property
    def unobservable(self) -> str:
        return "unobservable"


class MyBrokenThing(MyThing):
    @computed_property
    def broken(self) -> str:
        return self.unobservable


@pytest.fixture
def server():
    """Return a server with a MyThing attached."""
    server = lt.ThingServer.from_things({"thing": MyThing})
    return server


@pytest.fixture
async def aclient(server):
    """Create an asynchronous test client."""
    transport = ASGITransport(app=server.app)
    async with server.lifespan(server.app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as aclient:
            yield aclient


def test_running_without_event_loop(mocker):
    """The computed properties should work as expected without an event loop."""
    thing = create_thing_without_server(MyThing)

    thing.quantity = 1
    assert thing.double == 2

    assert thing.selected == 1

    thing.selector = "q2"
    thing.quantity2 = 10
    assert thing.selected == 10


def test_dependencies():
    """Test that the right dependencies are detected when we recompute the property."""
    thing = create_thing_without_server(MyThing)

    thing.quantity = 1
    assert MyThing.double.recompute(thing) == (2, {"quantity"})
    thing.selector = "q1"
    assert MyThing.selected.recompute(thing) == (1, {"selector", "quantity"})

    thing.selector = "q2"
    thing.quantity2 = 10
    assert MyThing.selected.recompute(thing) == (10, {"selector", "quantity2"})


def test_unobservable():
    """Check computed properties error if they depend on unobservable quantities."""
    thing = create_thing_without_server(MyBrokenThing)
    with pytest.raises(PropertyNotObservableError):
        MyBrokenThing.broken.recompute(thing)


async def test_notifications_double(server, aclient):
    """Check that we get a notification if a dependent property changes."""
    thing = server.things["thing"]
    assert isinstance(thing, MyThing)

    # Subscribe to updates from "double"
    send, recv = anyio.create_memory_object_stream[Message](max_buffer_size=1)
    await server.message_broker.subscribe("thing", "double", send)
    print("started")

    # Listen for updates and set `quantity` to trigger one
    async with anyio.create_task_group() as tg:
        handle = tg.start_soon(recv.receive)
        await run_sync(thing.properties["quantity"].set, 42)
    message = handle.return_value

    # Check the message described the update properly
    assert message.affordance == "double"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == 84


async def test_notifications_selected(server, aclient):
    """Check that we get a notification if a dependent property changes."""
    thing = server.things["thing"]
    assert isinstance(thing, MyThing)

    # Subscribe to updates from "selected"
    send, recv = anyio.create_memory_object_stream[Message](max_buffer_size=2)
    await server.message_broker.subscribe("thing", "selected", send)

    # Set `quantity` to trigger a recomputation and a message
    await run_sync(thing.properties["quantity"].set, 42)
    message = await recv.receive()
    print("changed quantity")

    # Check the message described the update properly
    assert message.affordance == "selected"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == 42

    # Setting `quantity2` should not trigger an update.
    await run_sync(thing.properties["quantity2"].set, 1)
    await anyio.sleep(0.05)
    with pytest.raises(anyio.WouldBlock):
        # There should be no message in the receive stream
        recv.receive_nowait()
    print("changed quantity2")

    # Change the value of `quantity2` to guard against
    # messages sitting in the stream. This shouldn't notify,
    # because  quantity2 is not yet a dependency
    await run_sync(thing.properties["quantity2"].set, 2)
    # Now change `selector`, which should trigger a recomputation.
    await run_sync(thing.properties["selector"].set, "q2")
    message = await recv.receive()

    # Check the message described the update properly
    assert message.affordance == "selected"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == 2

    # `quantity2` should now be a dependency, so it ought to trigger
    # an update.
    await run_sync(thing.properties["quantity2"].set, 3)
    message = await recv.receive()

    # Check the message described the update properly
    assert message.affordance == "selected"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == 3

    # Setting `quantity` should not trigger an update any more.
    await run_sync(thing.properties["quantity"].set, 1)
    await anyio.sleep(0.05)
    with pytest.raises(anyio.WouldBlock):
        # There should be no message in the receive stream
        recv.receive_nowait()
