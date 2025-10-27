import pytest
import labthings_fastapi as lt
from fastapi.testclient import TestClient


class LifecycleThing(lt.Thing):
    alive: bool = lt.property(default=False)
    "Whether the thing is alive."

    def __enter__(self):
        print("setting up TestThing from __enter__")
        self.alive = True
        return self

    def __exit__(self, *args):
        print("closing TestThing from __exit__")
        self.alive = False


@pytest.fixture
def server():
    """A ThingServer with a LifecycleThing."""
    return lt.ThingServer({"thing": LifecycleThing})


@pytest.fixture
def thing(server):
    """The thing attached to our server."""
    return server.things["thing"]


def test_thing_alive(server, thing):
    assert thing.alive is False
    with TestClient(server.app) as client:
        assert thing.alive is True
        r = client.get("/thing/alive")
        assert r.json() is True
    assert thing.alive is False


def test_thing_alive_twice(server, thing):
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
