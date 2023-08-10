from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.thing import Thing
from fastapi.testclient import TestClient
from labthings_fastapi.thing_server import ThingServer

class TestThing(Thing):
    alive = PropertyDescriptor(bool, False, description="Is the thing alive?")
    def __enter__(self):
        self.alive = True
        return self
    def __exit__(self, *args):
        self.alive = False
    

thing = TestThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def test_action_output():
    assert thing.alive is False
    with TestClient(server.app) as client:
        r = client.get("/thing/alive")
        assert r.json() is True
    assert thing.alive is False
