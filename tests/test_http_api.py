from fastapi.testclient import TestClient
from labthings_fastapi.thing_server import ThingServer
from test_thing import MyThing
from temp_client import poll_task, get_link

my_thing = MyThing()
server = ThingServer()
server.add_thing(my_thing, "/my_thing")


def test_property_get_and_set():
    client = TestClient(server.app)
    test_str = "A silly test string"
    r = client.post("/my_thing/foo", json=test_str)
    print(r)
    after_value = client.get("/my_thing/foo")
    assert after_value.json() == test_str


def test_counter():
    client = TestClient(server.app)
    before_value = client.get("/my_thing/counter").json()
    r = client.post("/my_thing/increment_counter", json={})
    # TODO: the above shouldn't need a payload at all...
    assert r.status_code in (200, 201)
    poll_task(client, r.json())
    after_value = client.get("/my_thing/counter").json()
    assert after_value == before_value + 1


def test_action_output():
    client = TestClient(server.app)
    r = client.post("/my_thing/make_a_dict", json={})
    invocation = poll_task(client, r.json())
    assert invocation["status"] == "completed"
    assert invocation["output"] == {"key": "value"}
    r = client.get(get_link(invocation, "output")["href"])
    assert r.json() == {"key": "value"}
