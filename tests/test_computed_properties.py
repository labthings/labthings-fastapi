"""Test computed properties in isolation."""

from typing import Any, Literal

import anyio
import pytest
from anyio.to_thread import run_sync
from httpx2 import ASGITransport, AsyncClient

import labthings_fastapi as lt
from labthings_fastapi.computed_properties import (
    ComputedProperty,
    access_wrapper,
    computed_property,
    start_watching_computed_properties,
)
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

    @property
    def non_labthings_property(self) -> int:
        """An attribute that's not a LabThings property."""
        return 99


class MyBrokenThing(MyThing):
    @computed_property
    def broken(self) -> str:
        return self.unobservable


class RecursionBomb(lt.Thing):
    @computed_property
    def a(self) -> str:
        return self.b + " blah"

    @computed_property
    def b(self) -> str:
        return self.a + "blah"


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


def test_access_wrapper():
    """Test the access wrapper works as expected."""
    thing = create_thing_without_server(MyThing)
    accesses: list[str] = []
    expected_accesses: list[str] = []
    wrapper = access_wrapper(thing, accesses.append)

    # Accessing an observable property should:
    # 1. call the callback, i.e. append the name
    # 2. return the value of the property
    assert wrapper.quantity == 0
    expected_accesses.append("quantity")
    assert accesses == expected_accesses

    # Check that the object and wrapper stay in sync
    thing.quantity = 1
    assert wrapper.quantity == 1
    expected_accesses.append("quantity")
    assert accesses == expected_accesses

    # Computed properties are observable and thus allowed
    assert wrapper.double == 2
    expected_accesses.append("double")
    assert accesses == expected_accesses

    # The wrapper should not allow attribute writes
    with pytest.raises(AttributeError):
        wrapper.quantity = -1

    # The wrapper should not allow attribute access to
    # anything other than observable properties
    with pytest.raises(PropertyNotObservableError):
        _ = wrapper.unobservable
    with pytest.raises(TypeError, match="is not a property"):
        _ = wrapper.non_labthings_property


def test_running_without_event_loop():
    """The computed properties should work as expected without an event loop.

    The property is recomputed each time it's accessed.
    """
    thing = create_thing_without_server(MyThing)

    thing.quantity = 1
    assert thing.double == 2

    assert thing.selected == 1

    thing.selector = "q2"
    thing.quantity2 = 10
    assert thing.selected == 10


def recompute(obj: lt.Thing, name: str) -> tuple[Any, set[str]]:
    """Recompute a computed property and output the dependencies.

    This duplicates logic that lives in `ComputedProperty._watch_for_changes`
    so we can run it in isolation to test the access wrapper. It didn't make
    sense to put this in a function, because these 4 lines of code are spread
    over a for loop in the `ComputedProperty` function, which isn't needed
    here.

    :prop obj: the Thing we're working with.
    :prop name: the name of the property.
    :return: the value of the property, and a set of the names of its
        dependencies.
    """
    dependencies: set[str] = set()
    wrapper = access_wrapper(obj, callback=dependencies.add)
    prop = obj.properties[name].get_descriptor()
    assert isinstance(prop, ComputedProperty)
    # This will compute the value, and populate `dependencies` via the callback
    value = prop.fget(wrapper)
    return value, dependencies


def test_dependencies():
    """Test that the right dependencies are detected when we recompute the property."""
    thing = create_thing_without_server(MyThing)

    thing.quantity = 1
    assert recompute(thing, "double") == (2, {"quantity"})
    thing.selector = "q1"
    assert recompute(thing, "selected") == (1, {"selector", "quantity"})

    thing.selector = "q2"
    thing.quantity2 = 10
    assert recompute(thing, "selected") == (10, {"selector", "quantity2"})


def test_unobservable():
    """Check computed properties error if they depend on unobservable quantities."""
    thing = create_thing_without_server(MyBrokenThing)
    with pytest.raises(PropertyNotObservableError):
        recompute(thing, "broken")


async def test_notifications_double(server, aclient):
    """Check that we get a notification if a dependent property changes.

    This test also verifies that the cached value is being updated.
    """
    thing = server.things["thing"]
    assert isinstance(thing, MyThing)
    prop = thing.properties["double"].get_descriptor()
    assert isinstance(prop, ComputedProperty)

    # This test uses `aclient` so the computed property should already have
    # been initialised, meaning the cache should be active
    assert thing.double == 0  # the default value
    assert prop._latest_values[thing] == 0  # check cache explicitly

    # Subscribe to updates from "double"
    send, recv = anyio.create_memory_object_stream[Message](max_buffer_size=1)
    await server.message_broker.subscribe("thing", "double", send)

    # Listen for updates and set `quantity` to trigger one
    # Note that we need a task group because we must start
    # listening before we set the property, otherwise the buffer overflows.
    # This most closely matches the way notifications will work in a
    # real server - we could also use a bigger buffer and do it sequentially,
    # which is done in the next test.
    async with anyio.create_task_group() as tg:
        handle = tg.start_soon(recv.receive)
        await run_sync(thing.properties["quantity"].set, 42)
        expected_value = 84
    message = handle.return_value

    # Check the message described the update properly
    assert message.affordance == "double"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == expected_value

    # Check the computed property now has the right value
    assert thing.double == expected_value
    # Explicitly check that the cache is up to date
    assert prop._latest_values[thing] == expected_value


async def test_notifications_publish(server, aclient):
    """Check that publishing a computed property recomputes it."""
    thing = server.things["thing"]
    assert isinstance(thing, MyThing)

    # Subscribe to updates from "double"
    send, recv = anyio.create_memory_object_stream[Message](max_buffer_size=2)
    await server.message_broker.subscribe("thing", "double", send)

    for _ in range(3):
        # Publish its value explicitly
        await run_sync(thing.properties["double"].publish)
        message = await recv.receive()
        # Note: we do this 3 times to make sure the messages weren't somehow
        # buffered in the stream from start-up: 3 is bigger than the buffer
        # size.

    # Check the message described the update properly
    assert message.affordance == "double"
    assert message.thing == "thing"
    assert message.message_type == "property"
    assert message.payload == 0


async def test_notifications_selected(server, aclient):
    """Check that we get a notification if a dependent property changes."""
    thing = server.things["thing"]
    assert isinstance(thing, MyThing)

    # Subscribe to updates from "selected"
    # Note: we use a buffer size of 2 so we can call `recv.receive()` *after*
    # we trigger the update. This avoids the need to use a task group every
    # time. We test using a buffer size of 1 in test_notifications_double.
    send, recv = anyio.create_memory_object_stream[Message](max_buffer_size=2)
    await server.message_broker.subscribe("thing", "selected", send)

    # Set `quantity` to trigger a recomputation and a message
    await run_sync(thing.properties["quantity"].set, 42)
    message = await recv.receive()

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


def test_recursion_noloop():
    """Two computed properties that depend on each other form an infinite loop.

    This would be a recursion problem even if they were just regular properties.
    This test can be safely skipped if it turns out to be slow, but it felt
    appropriate to demonstrate that it's a RecursionError even without any
    of the computed property code running (without the event loop, there should
    be no difference between this and a regular property).
    """
    thing = create_thing_without_server(RecursionBomb)
    with pytest.raises(RecursionError):
        _ = thing.a


def test_recursion_in_server():
    """Computed properties that form an infinite loop should crash the server.

    This isn't a problem that's unique to computed properties, so I don't think
    there is any need to specifically guard against it: it would be an error
    if it was just a plain `builtins.property` (see above test).
    """
    server = lt.ThingServer.from_things({"thing": RecursionBomb})
    with pytest.RaisesGroup(RecursionError, flatten_subgroups=True):
        with server.test_client():
            pass


async def test_start_watching_computed_properties(mocker):
    """Check the function to watch all computed properties on a Thing works.

    This checks that the relevant coroutine was started for each computed
    property.
    """
    thing = create_thing_without_server(MyThing)
    tg = mocker.AsyncMock()
    await start_watching_computed_properties(thing, tg)
    assert tg.start.call_count == 2
    assert await tg.start.has_awaits(
        [
            mocker.call(
                thing.properties["double"].get_descriptor()._watch_for_changes, thing
            ),
            mocker.call(
                thing.properties["selected"].get_descriptor()._watch_for_changes, thing
            ),
        ]
    )


async def test_start_watching_computed_properties_error(mocker):
    """Check the error condition on start_watching_computed_properties.

    This should only be possible if someone creates a property that
    claims to be computed, but isn't a ComputedProperty.
    """

    class BadProp(lt.DataProperty[lt.Thing, int]):
        is_computed: bool = True

    class BadThing(lt.Thing):
        bad: int = BadProp(default=0)  # type: ignore

    thing = create_thing_without_server(BadThing)
    tg = mocker.AsyncMock()
    with pytest.raises(TypeError):
        await start_watching_computed_properties(thing, tg)
