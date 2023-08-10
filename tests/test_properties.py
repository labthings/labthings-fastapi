from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.decorators import thing_property
from labthings_fastapi.thing import Thing
from fastapi.testclient import TestClient
from labthings_fastapi.thing_server import ThingServer

class TestThing(Thing):
    boolprop = PropertyDescriptor(bool, False, description="A boolean property")

    _undoc = None
    @thing_property
    def undoc(self):
        return self._undoc
    
    _float = 1.0
    @thing_property
    def floatprop(self):
        return self._float
    @floatprop.setter
    def floatprop(self, value: float):
        self._float = value
    
    
    

thing = TestThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def test_propertydescriptor():
    with TestClient(server.app) as client:
        r = client.get("/thing/boolprop")
        assert r.json() is False
        client.post("/thing/boolprop", json=True)
        r = client.get("/thing/boolprop")
        assert r.json() is True

def test_decorator_with_no_annotation():
    with TestClient(server.app) as client:
        r = client.get("/thing/undoc")
        assert r.json() is None
        r = client.post("/thing/undoc", json="foo")
        assert r.status_code != 200

def test_readwrite_with_getter_and_setter():
    with TestClient(server.app) as client:
        r = client.get("/thing/floatprop")
        assert r.json() == 1.0
        r = client.post("/thing/floatprop", json=2.0)
        assert r.status_code == 201
        r = client.get("/thing/floatprop")
        assert r.json() == 2.0
        r = client.post("/thing/floatprop", json="foo")
        assert r.status_code != 200