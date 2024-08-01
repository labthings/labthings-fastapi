from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.decorators import thing_property, thing_action
from labthings_fastapi.thing import Thing
from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer
from threading import Thread
from pytest import raises
from pydantic import BaseModel


class TestThing(Thing):
    boolprop = PropertyDescriptor(bool, False, description="A boolean property")
    stringprop = PropertyDescriptor(str, "foo", description="A string property")

    _undoc = None

    @thing_property
    def undoc(self):
        return self._undoc

    _float = 1.0

    @thing_property
    def floatprop(self) -> float:
        return self._float

    @floatprop.setter
    def floatprop(self, value: float):
        self._float = value

    @thing_action
    def toggle_boolprop(self):
        self.boolprop = not self.boolprop

    @thing_action
    def toggle_boolprop_from_thread(self):
        t = Thread(target=self.toggle_boolprop)
        t.start()


thing = TestThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def test_instantiation_with_type():
    prop = PropertyDescriptor(bool, False)
    assert issubclass(prop.model, BaseModel)


def test_instantiation_with_model():
    class MyModel(BaseModel):
        a: int = 1
        b: float = 2.0

    prop = PropertyDescriptor(MyModel, MyModel())
    assert prop.model is MyModel


def test_property_get_and_set():
    with TestClient(server.app) as client:
        test_str = "A silly test string"
        client.put("/thing/stringprop", json=test_str)
        after_value = client.get("/thing/stringprop")
        assert after_value.json() == test_str


def test_propertydescriptor():
    with TestClient(server.app) as client:
        r = client.get("/thing/boolprop")
        assert r.json() is False
        client.put("/thing/boolprop", json=True)
        r = client.get("/thing/boolprop")
        assert r.json() is True


def test_decorator_with_no_annotation():
    with TestClient(server.app) as client:
        r = client.get("/thing/undoc")
        assert r.json() is None
        r = client.put("/thing/undoc", json="foo")
        assert r.status_code != 200


def test_readwrite_with_getter_and_setter():
    with TestClient(server.app) as client:
        r = client.get("/thing/floatprop")
        assert r.json() == 1.0
        r = client.put("/thing/floatprop", json=2.0)
        assert r.status_code == 201
        r = client.get("/thing/floatprop")
        assert r.json() == 2.0
        r = client.put("/thing/floatprop", json="foo")
        assert r.status_code != 200


def test_sync_action():
    with TestClient(server.app) as client:
        client.put("/thing/boolprop", json=False)
        r = client.get("/thing/boolprop")
        assert r.json() is False
        r = client.post("/thing/toggle_boolprop", json={})
        assert r.status_code in [200, 201]
        r = client.get("/thing/boolprop")
        assert r.json() is True


def test_setting_from_thread():
    with TestClient(server.app) as client:
        client.put("/thing/boolprop", json=False)
        r = client.get("/thing/boolprop")
        assert r.json() is False
        r = client.post("/thing/toggle_boolprop_from_thread", json={})
        assert r.status_code in [200, 201]
        r = client.get("/thing/boolprop")
        assert r.json() is True


def test_setting_without_event_loop():
    # This test may need to change, if we change the intended behaviour
    # Currently it should never be necessary to change properties from the
    # main thread, so we raise an error if you try to do so
    with raises(RuntimeError):
        thing.boolprop = False  # Can't call it until the event loop's running
