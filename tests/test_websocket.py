from fastapi.testclient import TestClient
from labthings_fastapi.thing_server import ThingServer
from test_thing import MyThing

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
