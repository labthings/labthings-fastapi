from fastapi.testclient import TestClient
import pytest
import labthings_fastapi as lt
from labthings_fastapi.exceptions import PropertyNotObservableError


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

    This doesn't check the observation works, because we don't
    have an event loop. It just checks the call doesn't raise
    an error.
    """
    thing.observe_property("dataprop", mocker.Mock())


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
    """Check observing an action is successful."""
    thing.observe_action("increment_dataprop", mocker.Mock())


def test_observing_action_error(thing, mocker):
    """Check observing an attribute that's not an action raises an error."""
    with pytest.raises(KeyError):
        thing.observe_action("non_property", mocker.Mock())


def test_observing_action_with_ws(client, ws):
    """Observe an action with a websocket, checking the status changes correctly."""
    # Observe the property.
    ws.send_json(
        {
            "messageType": "addActionObservation",
            "data": {"increment_dataprop": True},
        }
    )
    # Invoke the action (via HTTP)
    client.post("/thing/increment_dataprop")
    # We should see the status go through the expected sequence
    for expected_status in ["pending", "running", "completed"]:
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
