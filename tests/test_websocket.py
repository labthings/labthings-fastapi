from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer
from labthings_fastapi.example_things import MyThing

my_thing = MyThing()
server = ThingServer()
server.add_thing(my_thing, "/my_thing")


def test_websocket_observeproperty():
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


def test_websocket_observeproperty_counter():
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


def test_websocket_observeaction():
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
