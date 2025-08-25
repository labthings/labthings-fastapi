from fastapi.testclient import TestClient
import pytest
import labthings_fastapi as lt
from labthings_fastapi.exceptions import (
    PropertyNotObservableError,
    InvocationCancelledError,
)


class ThingWithProperties(lt.Thing):
    """A Thing with various different properties and actions.

    This is used by the earlier tests, ensuring properties may
    be observed.
    """

    dataprop: int = lt.property(default=0)
    non_property: int = 0

    @lt.property
    def funcprop(self) -> int:
        return 0

    @funcprop.setter
    def set_funcprop(self, val: int) -> None:
        pass

    @lt.thing_action
    def increment_dataprop(self):
        """Increment the data property."""
        self.dataprop += 1

    @lt.thing_action
    def raise_error(self):
        r"""Raise an exception to test for error status."""
        self.dataprop += 1
        raise Exception("A deliberate failure.")

    @lt.thing_action
    def cancel_myself(self):
        """Increment the data property, then pretend to be cancelled."""
        self.dataprop += 1
        raise InvocationCancelledError()


@pytest.fixture
def thing():
    """Instantiate and return a test Thing."""
    return ThingWithProperties()


@pytest.fixture
def server(thing):
    """Create a server, and add a MyThing test Thing to it."""
    server = lt.ThingServer()
    server.add_thing(thing, "/thing")
    return server


@pytest.fixture
def client(server):
    """Yield a TestClient connected to the server."""
    with TestClient(server.app) as client:
        yield client


@pytest.fixture
def ws(client):
    """Yield a websocket connection to a server hosting a MyThing().

    This ensures the websocket is properly closed after the test, and
    avoids lots of indent levels.
    """
    with client.websocket_connect("/thing/ws") as ws:
        try:
            yield ws
        finally:
            ws.close(1000)
            pass


def test_observing_dataprop(thing, mocker):
    """Check `observe_property` is OK on a data property.

    This checks that something is added to the set of observers.
    We don't check for events, as there's no event loop: this is
    tested in `test_observing_dataprop_with_ws` below.
    """
    observers_set = ThingWithProperties.dataprop._observers_set(thing)
    fake_observer = mocker.Mock()
    thing.observe_property("dataprop", fake_observer)
    assert fake_observer in observers_set


@pytest.mark.parametrize(
    argnames=["name", "exception"],
    argvalues=[
        ("funcprop", PropertyNotObservableError),
        ("non_property", KeyError),
        ("increment_dataprop", KeyError),
        ("missing", KeyError),
    ],
)
def test_observing_errors(thing, mocker, name, exception):
    """Check errors are raised if we observe an unsuitable property."""
    with pytest.raises(exception):
        thing.observe_property(name, mocker.Mock())


def test_observing_dataprop_with_ws(client, ws):
    """Observe a data property with a websocket.

    This tests the property's value gets notified when it is
    set via PUT requests or via an action.
    """
    # Observe the property.
    ws.send_json(
        {
            "messageType": "addPropertyObservation",
            "data": {"dataprop": True},
        }
    )
    for val in [1, 10, 0]:
        # Set the property's value.
        client.put("/thing/dataprop", json=val)
        # Receive the message and check it's as expected.
        message = ws.receive_json(mode="text")
        assert message["messageType"] == "propertyStatus"
        assert message["data"]["dataprop"] == val
    # Increment the value with an action
    client.post("/thing/increment_dataprop")
    message = ws.receive_json(mode="text")
    assert message["messageType"] == "propertyStatus"
    assert message["data"]["dataprop"] == 1


@pytest.mark.parametrize(
    argnames=["name", "title", "status"],
    argvalues=[
        ("funcprop", "Not Observable", "403"),
        ("non_property", "Not Found", "404"),
        ("increment_dataprop", "Not Found", "404"),
        ("missing", "Not Found", "404"),
    ],
)
def test_observing_dataprop_error_with_ws(ws, name, title, status):
    """Try to observe a functional/missing property with a websocket.

    This should fail: functional properties are not observable.
    """
    # Observe the property.
    ws.send_json(
        {
            "messageType": "addPropertyObservation",
            "data": {name: True},
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
    observers_set = ThingWithProperties.increment_dataprop._observers_set(thing)
    fake_observer = mocker.Mock()
    thing.observe_action("increment_dataprop", fake_observer)
    assert fake_observer in observers_set


def test_observing_action_error(thing, mocker):
    """Check observing an attribute that's not an action raises an error."""
    with pytest.raises(KeyError):
        thing.observe_action("non_property", mocker.Mock())


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
            "messageType": "addActionObservation",
            "data": {name: True},
        }
    )
    # Invoke the action (via HTTP)
    client.post(f"/thing/{name}")
    # We should see the status go through the expected sequence
    for expected_status in ["pending", "running", final_status]:
        message = ws.receive_json(mode="text")
        assert message["messageType"] == "actionStatus"
        assert message["data"]["status"] == expected_status


def test_observing_action_error_with_ws(ws):
    """Try to observe something that's not an action, as an action.

    This should fail: observeAction should only work on actions.
    """
    # Observe the property.
    ws.send_json(
        {
            "messageType": "addActionObservation",
            "data": {"non_property": True},
        }
    )
    # Receive the message and check for the error.
    message = ws.receive_json(mode="text")
    assert message["error"]["title"] == "Not Found"
    assert message["error"]["status"] == "404"
