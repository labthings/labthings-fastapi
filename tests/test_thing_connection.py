"""Test the thing_connection module."""

import pytest
import labthings_fastapi as lt
from fastapi.testclient import TestClient

from labthings_fastapi.exceptions import ThingConnectionError, ThingNotConnectedError


class ThingOne(lt.Thing):
    """A class that will cause chaos if it can."""

    thing_two: "ThingTwo" = lt.thing_connection("thing_two")

    @lt.thing_action
    def say_hello(self) -> str:
        """An example function."""
        return "Hello from thing_one."

    @lt.thing_action
    def ask_other_thing(self) -> str:
        """Ask ThingTwo to say hello."""
        return self.thing_two.say_hello()


class ThingTwo(lt.Thing):
    """A class that relies on ThingOne."""

    thing_one: ThingOne = lt.thing_connection("thing_one")

    @lt.thing_action
    def say_hello(self) -> str:
        """An example function."""
        return "Hello from thing_two."

    @lt.thing_action
    def ask_other_thing(self) -> str:
        """Ask ThingOne to say hello."""
        return self.thing_one.say_hello()


class ThingN(lt.Thing):
    """A class that emulates ThingOne and ThingTwo more generically."""

    other_thing: "ThingN" = lt.thing_connection()

    @lt.thing_action
    def say_hello(self) -> str:
        """An example function."""
        return f"Hello from {self.name}."

    @lt.thing_action
    def ask_other_thing(self) -> str:
        """Ask the other thing to say hello."""
        return self.other_thing.say_hello()


CONNECTIONS = {
    "thing_one": {"other_thing": "thing_two"},
    "thing_two": {"other_thing": "thing_one"},
}


@pytest.mark.parametrize(
    ("cls_1", "cls_2", "connections"),
    [
        (ThingOne, ThingTwo, None),
        (ThingOne, ThingTwo, CONNECTIONS),
        (ThingN, ThingN, CONNECTIONS),
    ],
)
def test_thing_connection(cls_1, cls_2, connections) -> None:
    """Check that two things can connect to each other.

    Note that this test includes a circular dependency, which is fine.
    No checks are made for infinite loops: that's up to the author of the
    Thing classes. Circular dependencies should not cause any problems for
    the LabThings server.
    """
    server = lt.ThingServer()
    thing_one = server.add_thing("thing_one", cls_1)
    thing_two = server.add_thing("thing_two", cls_2)
    things = [thing_one, thing_two]
    numbers = ["one", "two"]
    if connections is not None:
        server.thing_connections = connections

    # Check the things say hello correctly
    for thing, num in zip(things, numbers, strict=True):
        assert thing.say_hello() == f"Hello from thing_{num}."

    # Check the connections don't work initially, because they aren't connected
    for thing in things:
        with pytest.raises(ThingNotConnectedError):
            thing.ask_other_thing()

    with TestClient(server.app) as client:
        # The things should be connected as the server is now running

        # Check the things are connected, calling actions directly
        for thing, num in zip(things, reversed(numbers), strict=True):
            assert thing.ask_other_thing() == f"Hello from thing_{num}."

        # Check the same happens over "HTTP" (i.e. the TestClient)
        for num, othernum in zip(numbers, reversed(numbers), strict=True):
            thing = lt.ThingClient.from_url(f"/thing_{num}/", client=client)
            assert thing.ask_other_thing() == f"Hello from thing_{othernum}."
            assert thing.say_hello() == f"Hello from thing_{num}."


@pytest.mark.parametrize(
    ("connections", "error"),
    [
        # No default, no configuration - error should say so.
        (None, "no default"),
        # Configured to connect to a missing thing
        ({"thing_one": {"other_thing": "non_existent_thing"}}, "does not exist"),
        # Configured to connect to a thing that exists, but is the wrong type
        ({"thing_one": {"other_thing": "thing_two"}}, "must be of type"),
    ],
)
def test_thing_connection_errors(connections, error) -> None:
    """Check that a ThingConnection without a default raises an error."""
    server = lt.ThingServer()
    server.add_thing("thing_one", ThingN)
    server.add_thing("thing_two", ThingTwo)

    if connections is not None:
        server.thing_connections = connections

    with pytest.RaisesGroup(ThingConnectionError) as excinfo:
        # Creating a TestClient should activate the connections
        with TestClient(server.app):
            pass
    # excinfo contains an ExceptionGroup because TestClient runs in a
    # task group, hence the use of RaisesGroup and the `.exceptions[0]`
    # below.
    assert error in str(excinfo.value.exceptions[0])
