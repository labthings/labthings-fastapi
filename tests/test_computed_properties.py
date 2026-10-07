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


async def test_notifications(server, aclient):
    """Check that we get a notification if a dependent property changes."""
    thing = server.things["thing"]
    assert isinstance(thing, MyThing)

    send, recv = anyio.create_memory_object_stream[Message](max_buffer_size=1)
    await server.message_broker.subscribe("thing", "double", send)
    async with anyio.create_task_group() as tg:
        handle = tg.start_soon(recv.receive)
        await run_sync(thing.properties["quantity"].set, 42)
    message = handle.return_value

    assert message.affordance == "double"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == 84
