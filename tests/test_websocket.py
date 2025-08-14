from fastapi.testclient import TestClient
from labthings_fastapi.example_things import MyThing
import pytest
import labthings_fastapi as lt
from labthings_fastapi.exceptions import PropertyNotObservableError


@pytest.fixture
def my_thing():
    return MyThing()


@pytest.fixture
def server(my_thing):
    server = lt.ThingServer()
    server.add_thing(my_thing, "/my_thing")
    return server


def test_websocket_observeproperty(server):
    with TestClient(server.app) as client:
        with client.websocket_connect("/my_thing/ws") as ws:
            ws.send_json(
                {"messageType": "addPropertyObservation", "data": {"foo": True}}
            )
            test_str = "Abcdef"
            client.put("/my_thing/foo", json=test_str)
            message = ws.receive_json(mode="text")
            assert message["data"]["foo"] == test_str
            ws.close(1000)


class ThingWithProperties(lt.Thing):
    dataprop: int = lt.property(default=0)
    non_property: int = 0

    @lt.property
    def funcprop(self) -> int:
        return 0

    @lt.property
    def set_funcprop(self, val: int) -> None:
        pass

    @lt.thing_action
    def increment_dataprop(self):
        """Increment the data property."""
        self.dataprop += 1


def test_observing_dataprop(mocker):
    """Check `observe_property` is OK on a data property.

    This doesn't check the observation works, because we don't
    have an event loop. It just checks the call doesn't raise
    an error.
    """
    thing = ThingWithProperties()
    thing.observe_property("dataprop", mocker.Mock())


def test_observing_dataprop_with_ws():
    """Observe a data property with a websocket, and check it works."""
    server = lt.ThingServer()
    server.add_thing(ThingWithProperties(), "/thing")
    with TestClient(server.app) as client:
        with client.websocket_connect("/thing/ws") as ws:
            ws.send_json(
                {"messageType": "addPropertyObservation", "data": {"dataprop": True}}
            )
            client.put("/thing/dataprop", json=1)
            message = ws.receive_json(mode="text")
            assert message["data"]["dataprop"] == 1
            ws.close(1000)


def test_observing_funcprop(mocker):
    """Check errors are raised if we observe an unsuitable property."""
    thing = ThingWithProperties()
    with pytest.raises(PropertyNotObservableError):
        thing.observe_property("funcprop", mocker.Mock())


def test_observing_funcprop_with_ws():
    """Try to observe a functional property with a websocket.

    This should fail: functional properties are not observable.
    """
    server = lt.ThingServer()
    server.add_thing(ThingWithProperties(), "/thing")
    with TestClient(server.app) as client:
        with client.websocket_connect("/thing/ws") as ws:
            ws.send_json(
                {"messageType": "addPropertyObservation", "data": {"funcprop": True}}
            )
            message = ws.receive_json(mode="text")
            assert message["error"]["title"] == "Not Observable"
            ws.close(1000)


def test_observing_missing_prop(mocker):
    """Check observing a non-existent property raises an error."""
    thing = ThingWithProperties()
    with pytest.raises(AttributeError):
        thing.observe_property("missing_property", mocker.Mock())


def test_observing_not_prop(mocker):
    """Check observing an attribute that's not a property raises an error."""
    thing = ThingWithProperties()
    with pytest.raises(KeyError):
        thing.observe_property("non_property", mocker.Mock())


def test_observing_action(mocker):
    """Check observing an action is successful."""
    thing = ThingWithProperties()
    thing.observe_action("increment_dataprop", mocker.Mock())


def test_observing_not_action(mocker):
    """Check observing an attribute that's not an action raises an error."""
    thing = ThingWithProperties()
    with pytest.raises(KeyError):
        thing.observe_action("non_property", mocker.Mock())


def test_websocket_observeproperty_counter(server):
    with TestClient(server.app) as client:
        with client.websocket_connect("/my_thing/ws") as ws:
            ws.send_json(
                {"messageType": "addPropertyObservation", "data": {"counter": True}}
            )
            # Trigger the increment_counter action to change the counter value
            client.post("/my_thing/increment_counter")

            # Receive the message from the WebSocket
            message = ws.receive_json(mode="text")
            assert (
                message["data"]["counter"] == 1
            )  # Expect the counter to be 1 after increment
            ws.close(1000)
            my_thing.counter = 0  # Set counter back to 0


def handle_websocket_messages(message):
    if (
        message["messageType"] == "actionStatus"
        and message["data"]["status"] == "completed"
    ):
        return True
    return False


def test_websocket_observeaction(server, my_thing):
    with TestClient(server.app) as client:
        with client.websocket_connect("/my_thing/ws") as ws:
            ws.send_json(
                {"messageType": "addPropertyObservation", "data": {"counter": True}}
            )
            ws.send_json(
                {
                    "messageType": "addActionObservation",
                    "data": {"slowly_increase_counter": True},
                }
            )

            # Trigger the slowly_increase_counter action
            client.post("/my_thing/slowly_increase_counter", json={"delay": 0})

            # Listen for WebSocket messages and check for the completed action
            action_completed = False
            while not action_completed:
                message = ws.receive_json()
                print(f"Received message: {message}")

                action_completed = handle_websocket_messages(message)
                if action_completed:
                    assert my_thing.counter == 60

            my_thing.counter = 0  # Set counter back to 0
