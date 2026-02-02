from anyio import create_memory_object_stream
from fastapi.testclient import TestClient
from pydantic import BaseModel
import pytest
import labthings_fastapi as lt
from labthings_fastapi.exceptions import (
    PropertyNotObservableError,
    InvocationCancelledError,
)
from labthings_fastapi.testing import create_thing_without_server


class ThingWithProperties(lt.Thing):
    """A Thing with various different properties and actions.

    This is used by the earlier tests, ensuring properties may
    be observed.
    """

    dataprop: int = lt.property(default=0)
    non_property: int = 0

    def undecorated(self) -> int:
        """An undecorated function that returns an int."""
        return 0

    def python_property(self) -> int:
        """A property that isn't a LabThings property."""
        return 0

    @lt.property
    def funcprop(self) -> int:
        return 0

    @funcprop.setter
    def _set_funcprop(self, val: int) -> None:
        pass

    @lt.action
    def increment_dataprop(self):
        """Increment the data property."""
        self.dataprop += 1

    @lt.action
    def raise_error(self):
        r"""Raise an exception to test for error status."""
        self.dataprop += 1
        raise Exception("A deliberate failure.")

    @lt.action
    def cancel_myself(self):
        """Increment the data property, then pretend to be cancelled."""
        self.dataprop += 1
        raise InvocationCancelledError()


@pytest.fixture
def server():
    """Create a server, and add a MyThing test Thing to it."""
    server = lt.ThingServer({"thing": ThingWithProperties})
    return server


@pytest.fixture
def client(server):
    """Yield a TestClient connected to the server."""
    with TestClient(server.app) as client:
        yield client


@pytest.fixture
def ws(client):
    """Yield a websocket connection to a server hosting a MyThing.

    This ensures the websocket is properly closed after the test, and
    avoids lots of indent levels.
    """
    with client.websocket_connect("/thing/ws") as ws:
        try:
            yield ws
        finally:
            ws.close(1000)


@pytest.fixture
def thing():
    """Create a ThingWithProperties, not connected to a server."""
    return create_thing_without_server(ThingWithProperties)


def test_observing_dataprop(thing):
    """Check `observe_property` is OK on a data property.

    This checks that something is added to the set of observers.
    We don't check for events, as there's no event loop: this is
    tested in `test_observing_dataprop_with_ws` below.
    """
    send_stream, receive_stream = create_memory_object_stream[BaseModel]()
    thing.properties["dataprop"].observe(send_stream)
    event_broker = thing._thing_server_interface._event_broker
    observers_set = event_broker._subscriptions[thing.name]["dataprop"]
    assert send_stream in observers_set


@pytest.mark.parametrize(
    argnames=["name", "exception"],
    argvalues=[
        ("funcprop", PropertyNotObservableError),
        ("non_property", KeyError),
        ("python_property", KeyError),
        ("undecorated", KeyError),
        ("increment_dataprop", KeyError),
        ("missing", KeyError),
    ],
)
def test_observing_errors(thing, mocker, name, exception):
    """Check errors are raised if we observe an unsuitable property."""
    with pytest.raises(exception):
        thing.properties[name].observe(mocker.Mock())


def test_observing_dataprop_with_ws(client, ws):
    """Observe a data property with a websocket.

    This tests the property's value gets notified when it is
    set via PUT requests or via an action.
    """
    # Observe the property.
    ws.send_json(
        {
            "messageType": "request",
            "operation": "observeproperty",
            "name": "dataprop",
        }
    )
    for val in [1, 10, 0]:
        # Set the property's value.
        client.put("/thing/dataprop", json=val)
        # Receive the message and check it's as expected.
        message = ws.receive_json(mode="text")
        assert message["messageType"] == "notification"
        assert message["operation"] == "observeproperty"
        assert message["name"] == "dataprop"
        assert message["value"] == val
    # Increment the value with an action
    client.post("/thing/increment_dataprop")
    message = ws.receive_json(mode="text")
    assert message["messageType"] == "notification"
    assert message["operation"] == "observeproperty"
    assert message["name"] == "dataprop"
    assert message["value"] == 1


@pytest.mark.parametrize(
    argnames=["name", "title", "status"],
    argvalues=[
        ("funcprop", "Not Observable", 403),
        ("non_property", "Not Found", 404),
        ("python_property", "Not Found", 404),
        ("undecorated", "Not Found", 404),
        ("increment_dataprop", "Not Found", 404),
        ("missing", "Not Found", 404),
    ],
)
def test_observing_dataprop_error_with_ws(ws, name, title, status):
    """Try to observe a functional/missing property with a websocket.

    This should fail: functional properties are not observable.
    """
    # Observe the property.
    ws.send_json(
        {
            "messageType": "request",
            "operation": "observeproperty",
            "name": name,
        }
    )
    # Receive the message and check for the error.
    message = ws.receive_json(mode="text")
    assert message["error"]["title"] == title
    assert message["error"]["status"] == status


def test_observing_action(thing, mocker):
    """Check observing an action is successful.

    This verifies we've added an observer to the set, but doesn't test for
    notifications: that would require an event loop.
    """
    fake_observer = mocker.Mock()
    thing.actions["increment_dataprop"].observe(fake_observer)
    event_broker = thing._thing_server_interface._event_broker
    observers_set = event_broker._subscriptions[thing.name]["increment_dataprop"]
    assert fake_observer in observers_set


@pytest.mark.parametrize(
    "name", ["non_property", "python_property", "undecorated", "dataprop"]
)
def test_observing_action_error(thing, mocker, name):
    """Check observing an attribute that's not an action raises an error."""
    with pytest.raises(KeyError):
        thing.actions[name].observe(mocker.Mock())


@pytest.mark.parametrize(
    argnames=["name", "final_status"],
    argvalues=[
        ("increment_dataprop", "completed"),
        ("raise_error", "error"),
        ("cancel_myself", "cancelled"),
    ],
)
def test_observing_action_with_ws(client, ws, name, final_status):
    """Observe an action with a websocket, checking the status changes correctly."""
    # Observe the property.
    ws.send_json(
        {
            "messageType": "request",
            "operation": "observeaction",
            "name": name,
        }
    )
    # Invoke the action (via HTTP)
    client.post(f"/thing/{name}")
    # We should see the status go through the expected sequence
    for expected_status in ["pending", "running", final_status]:
        message = ws.receive_json(mode="text")
        assert message["messageType"] == "notification"
        assert message["operation"] == "observeaction"
        assert message["name"] == name
        assert message["status"] == expected_status


@pytest.mark.parametrize(
    "name", ["non_property", "python_property", "undecorated", "dataprop"]
)
def test_observing_action_error_with_ws(ws, name):
    """Try to observe something that's not an action, as an action.

    This should fail: observeAction should only work on actions.
    """
    # Observe the property.
    ws.send_json(
        {
            "messageType": "request",
            "operation": "observeaction",
            "name": name,
        }
    )
    # Receive the message and check for the error.
    message = ws.receive_json(mode="text")
    assert message["error"]["title"] == "Not Found"
    assert message["error"]["status"] == 404
