"""Test that Thing Client's can call actions and read properties."""

from httpx import HTTPStatusError
import pytest
import labthings_fastapi as lt
from fastapi.testclient import TestClient


class ThingToTest(lt.Thing):
    """A thing to be tested by using a ThingClient."""

    int_prop: int = lt.property(default=1)
    float_prop: float = lt.property(default=0.1)
    str_prop: str = lt.property(default="foo")

    int_prop_read_only: int = lt.property(default=1, readonly=True)
    float_prop_read_only: float = lt.property(default=0.1, readonly=True)
    str_prop_read_only: str = lt.property(default="foo", readonly=True)

    @lt.action
    def increment(self) -> None:
        """Increment the counter.

        An action with no arguments or return.
        """
        self.int_prop += 1

    @lt.action
    def increment_and_return(self) -> int:
        """Increment the counter and return value.

        An action with no arguments, but with a return value
        """
        self.int_prop += 1
        return self.int_prop

    @lt.action
    def increment_by_input(self, value: int = 1) -> None:
        """Increment the counter by input value.

        An action with an argument but no return.
        """
        self.int_prop += value

    @lt.action
    def increment_by_input_and_return(self, value: int = 1) -> int:
        """Increment the counter by input value and return the new value.

        An action with and argument and a return value.
        """
        self.int_prop += value
        return self.int_prop


@pytest.fixture
def thing_client():
    """Yield a test client connected to a ThingServer."""
    server = lt.ThingServer({"test_thing": ThingToTest})
    with TestClient(server.app) as client:
        yield lt.ThingClient.from_url("/test_thing/", client=client)


def test_reading_and_setting_properties(thing_client):
    """Test reading and setting properties."""
    assert thing_client.int_prop == 1
    assert thing_client.float_prop == 0.1
    assert thing_client.str_prop == "foo"

    thing_client.int_prop = 2
    thing_client.float_prop = 0.2
    thing_client.str_prop = "foo2"

    assert thing_client.int_prop == 2
    assert thing_client.float_prop == 0.2
    assert thing_client.str_prop == "foo2"


def test_reading_and_not_setting_read_only_properties(thing_client):
    """Test reading read_only properties, but failing to set."""
    assert thing_client.int_prop_read_only == 1
    assert thing_client.float_prop_read_only == 0.1
    assert thing_client.str_prop_read_only == "foo"

    with pytest.raises(HTTPStatusError, match="405 Method Not Allowed"):
        thing_client.int_prop_read_only = 2
    with pytest.raises(HTTPStatusError, match="405 Method Not Allowed"):
        thing_client.float_prop_read_only = 0.2
    with pytest.raises(HTTPStatusError, match="405 Method Not Allowed"):
        thing_client.str_prop_read_only = "foo2"

    assert thing_client.int_prop_read_only == 1
    assert thing_client.float_prop_read_only == 0.1
    assert thing_client.str_prop_read_only == "foo"


def test_call_action(thing_client):
    """Test calling an action."""
    assert thing_client.int_prop == 1
    thing_client.increment()
    assert thing_client.int_prop == 2


def test_call_action_with_return(thing_client):
    """Test calling an action with a return."""
    assert thing_client.int_prop == 1
    new_value = thing_client.increment_and_return()
    assert new_value == 2
    assert thing_client.int_prop == 2


def test_call_action_with_args(thing_client):
    """Test calling an action."""
    assert thing_client.int_prop == 1
    thing_client.increment_by_input(value=5)
    assert thing_client.int_prop == 6


def test_call_action_with_args_and_return(thing_client):
    """Test calling an action with a return."""
    assert thing_client.int_prop == 1
    new_value = thing_client.increment_by_input_and_return(value=5)
    assert new_value == 6
    assert thing_client.int_prop == 6
