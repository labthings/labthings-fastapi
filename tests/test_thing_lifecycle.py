from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.thing import Thing
from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer


class TestThing(Thing):
    alive = PropertyDescriptor(bool, False, description="Is the thing alive?")

    def __enter__(self):
        print("setting up TestThing from __enter__")
        self.alive = True
        return self

    def __exit__(self, *args):
        print("closing TestThing from __exit__")
        self.alive = False


thing = TestThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def test_thing_alive():
    assert thing.alive is False
    with TestClient(server.app) as client:
        r = client.get("/thing/alive")
        assert r.json() is True
    assert thing.alive is False


def test_thing_alive_twice():
    """It's unlikely we need to stop and restart the server within one
    Python session, except for testing. This test should explicitly make
    sure our lifecycle stuff is closing down cleanly and can restart.
    """
    assert thing.alive is False
    with TestClient(server.app) as client:
        r = client.get("/thing/alive")
        assert r.json() is True
    assert thing.alive is False
    with TestClient(server.app) as client:
        r = client.get("/thing/alive")
        assert r.json() is True
