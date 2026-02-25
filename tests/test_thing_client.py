"""Test that Thing Clients can call actions and read properties."""

import re

import pytest
import labthings_fastapi as lt
from fastapi.testclient import TestClient

from labthings_fastapi.exceptions import ClientPropertyError, FailedToInvokeActionError


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
    def increment_by_input(self, value: int) -> None:
        """Increment the counter by input value.

        An action with an argument but no return.
        """
        self.int_prop += value

    @lt.action
    def increment_by_input_and_return(self, value: int) -> int:
        """Increment the counter by input value and return the new value.

        An action with and argument and a return value.
        """
        self.int_prop += value
        return self.int_prop

    @lt.action
    def throw_value_error(self) -> None:
        """Throw a value error."""
        raise ValueError("This never works!")


@pytest.fixture
def thing_client_and_thing():
    """Yield a test client connected to a ThingServer and the Thing itself."""
    server = lt.ThingServer({"test_thing": ThingToTest})
    with TestClient(server.app) as client:
        thing_client = lt.ThingClient.from_url("/test_thing/", client=client)
        thing = server.things["test_thing"]
        yield thing_client, thing


@pytest.fixture
def thing_client(thing_client_and_thing):
    """Yield a test client connected to a ThingServer."""
    return thing_client_and_thing[0]


def test_reading_and_setting_properties(thing_client_and_thing):
    """Test reading and setting properties."""
    thing_client, thing = thing_client_and_thing

    # Read the properties from the thing
    assert thing_client.int_prop == 1
    assert thing_client.float_prop == 0.1
    assert thing_client.str_prop == "foo"

    # Update via thing client and check they change on the server and in the client
    thing_client.int_prop = 2
    thing_client.float_prop = 0.2
    thing_client.str_prop = "foo2"

    # Check the server updated
    assert thing.int_prop == 2
    assert thing.float_prop == 0.2
    assert thing.str_prop == "foo2"
    # Check the client updated
    assert thing_client.int_prop == 2
    assert thing_client.float_prop == 0.2
    assert thing_client.str_prop == "foo2"

    # Update them on the server side and read them again
    thing.int_prop = 3
    thing.float_prop = 0.3
    thing.str_prop = "foo3"
    assert thing_client.int_prop == 3
    assert thing_client.float_prop == 0.3
    assert thing_client.str_prop == "foo3"

    # Set a property that doesn't exist.
    err = "Failed to get property foobar: Not Found"
    with pytest.raises(ClientPropertyError, match=err):
        thing_client.get_property("foobar")

    # Set a property with bad data type.
    err = (
        "Failed to set property int_prop: Input should be a valid integer, unable to "
        "parse string as an integer"
    )
    with pytest.raises(ClientPropertyError, match=err):
        thing_client.int_prop = "Bad value!"


def test_reading_and_not_setting_read_only_properties(thing_client_and_thing):
    """Test reading read_only properties, but failing to set."""
    thing_client, thing = thing_client_and_thing
    assert thing_client.int_prop_read_only == 1
    assert thing_client.float_prop_read_only == 0.1
    assert thing_client.str_prop_read_only == "foo"

    with pytest.raises(ClientPropertyError, match="may not be set"):
        thing_client.int_prop_read_only = 2
    with pytest.raises(ClientPropertyError, match="may not be set"):
        thing_client.float_prop_read_only = 0.2
    with pytest.raises(ClientPropertyError, match="may not be set"):
        thing_client.str_prop_read_only = "foo2"

    assert thing_client.int_prop_read_only == 1
    assert thing_client.float_prop_read_only == 0.1
    assert thing_client.str_prop_read_only == "foo"


def test_property_descriptor_errors(mocker):
    """This checks that read/write-only properties raise an error when written/read.

    Write only properties are not yet supported on the server side, so it's done with a
    mocked up Thing Description.
    """
    thing_description = {
        "title": "Example",
        "properties": {
            "readwrite": {
                "title": "test",
                "writeOnly": False,
                "readOnly": False,
                "type": "integer",
                "forms": [],
            },
            "readonly": {
                "title": "test",
                "writeOnly": False,
                "readOnly": True,
                "type": "integer",
                "forms": [],
            },
            "writeonly": {
                "title": "test",
                "writeOnly": True,
                "readOnly": False,
                "type": "integer",
                "forms": [],
            },
        },
        "actions": {},
        "base": None,
        "securityDefinitions": {"no_security": {}},
        "security": "no_security",
    }

    # Create a client object
    MyClient = lt.ThingClient.subclass_from_td(thing_description)
    client = MyClient("/", mocker.Mock())
    # Mock the underlying get/set functions so we don't need a server
    mocker.patch.object(client, "get_property")
    client.get_property.return_value = 42
    mocker.patch.object(client, "set_property")

    # Check which properties we can read
    assert client.readwrite == 42
    assert client.readonly == 42
    with pytest.raises(ClientPropertyError, match="may not be read"):
        _ = client.writeonly
    assert client.get_property.call_count == 2

    # The same check for writing
    client.readwrite = 0
    client.writeonly = 0
    with pytest.raises(ClientPropertyError, match="may not be set"):
        _ = client.readonly = 0
    assert client.set_property.call_count == 2


def test_call_action(thing_client_and_thing):
    """Test calling an action."""
    thing_client, thing = thing_client_and_thing
    assert thing_client.int_prop == 1
    thing_client.increment()
    assert thing_client.int_prop == 2
    assert thing.int_prop == 2


def test_call_action_with_return(thing_client_and_thing):
    """Test calling an action with a return."""
    thing_client, thing = thing_client_and_thing
    assert thing_client.int_prop == 1
    new_value = thing_client.increment_and_return()
    assert new_value == 2
    assert thing_client.int_prop == 2
    assert thing.int_prop == 2


def test_call_action_with_args(thing_client_and_thing):
    """Test calling an action."""
    thing_client, thing = thing_client_and_thing
    assert thing_client.int_prop == 1
    thing_client.increment_by_input(value=5)
    assert thing_client.int_prop == 6
    assert thing.int_prop == 6


def test_call_action_with_args_and_return(thing_client_and_thing):
    """Test calling an action with a return."""
    thing_client, thing = thing_client_and_thing
    assert thing_client.int_prop == 1
    new_value = thing_client.increment_by_input_and_return(value=5)
    assert new_value == 6
    assert thing_client.int_prop == 6
    assert thing.int_prop == 6


def test_call_action_wrong_arg(thing_client):
    """Test calling an action with wrong argument."""
    err = "Error when invoking action increment_by_input: 'value' - Field required"

    with pytest.raises(FailedToInvokeActionError, match=err):
        thing_client.increment_by_input(input=5)


def test_call_action_wrong_type(thing_client):
    """Test calling an action with wrong argument."""
    err = (
        "Error when invoking action increment_by_input: 'value' - Input should be a "
        "valid integer, unable to parse string as an integer"
    )
    with pytest.raises(FailedToInvokeActionError, match=err):
        thing_client.increment_by_input(value="foo")


def test_call_that_errors(thing_client):
    """Test calling an action with wrong argument."""
    regex = r"Action throw_value_error \(ID: [0-9a-f\-]*\) failed with error:"
    with pytest.raises(lt.exceptions.ServerActionError, match=regex) as exc_info:
        thing_client.throw_value_error()

    full_message = str(exc_info.value)
    assert "[ValueError]: This never works!" in full_message
    assert "SERVER TRACEBACK START:" in full_message
    assert "SERVER TRACEBACK END" in full_message
    assert re.search(
        r'File ".*test_thing_client\.py", line \d+, in throw_value_error',
        full_message,
    )
