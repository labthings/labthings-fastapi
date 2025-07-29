from threading import Thread

from pytest import raises
from pydantic import BaseModel
from fastapi.testclient import TestClient

import labthings_fastapi as lt
from labthings_fastapi.exceptions import NotConnectedToServerError


class TestThing(lt.Thing):
    boolprop: bool = lt.property(default=False)
    "A boolean property"

    stringprop: str = lt.property(default="foo")
    "A string property"

    _undoc = None

    @lt.property
    def undoc(self):
        return self._undoc

    _float = 1.0

    @lt.property
    def floatprop(self) -> float:
        return self._float

    @floatprop.setter
    def floatprop(self, value: float):
        self._float = value

    @lt.thing_action
    def toggle_boolprop(self):
        self.boolprop = not self.boolprop

    @lt.thing_action
    def toggle_boolprop_from_thread(self):
        t = Thread(target=self.toggle_boolprop)
        t.start()


thing = TestThing()
server = lt.ThingServer()
server.add_thing(thing, "/thing")


def test_instantiation_with_type():
    """
    Check the internal model (data type) of the DataProperty descriptor is a BaseModel

    To send the data over HTTP LabThings-FastAPI uses Pydantic models to describe data
    types.
    """

    # This will not work unless the property is assigned to a thing
    class TestThing(lt.Thing):
        prop: bool = lt.property(default=False)

    assert issubclass(TestThing.prop.model, BaseModel)


def test_instantiation_with_model() -> None:
    class MyModel(BaseModel):
        a: int = 1
        b: float = 2.0

    class Dummy:
        prop: MyModel = lt.property(default=MyModel())

        @lt.property
        def func_prop(self) -> MyModel:
            return MyModel()

    assert Dummy.prop.model is MyModel  # type: ignore[attr-defined]
    # Dummy.prop is typed as MyModel, but it's a descriptor

    assert Dummy.func_prop.model is MyModel


def test_property_get_and_set():
    with TestClient(server.app) as client:
        test_str = "A silly test string"
        client.put("/thing/stringprop", json=test_str)
        after_value = client.get("/thing/stringprop")
        assert after_value.json() == test_str


def test_boolprop():
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
    """Test that an exception is raised if updating a DataProperty
    without connecting the Thing to a running server with an event loop.
    """
    # This test may need to change, if we change the intended behaviour
    # Currently it should never be necessary to change properties from the
    # main thread, so we raise an error if you try to do so
    with raises(NotConnectedToServerError):
        thing.boolprop = False  # Can't call it until the event loop's running
