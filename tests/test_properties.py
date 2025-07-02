from threading import Thread

from pytest import raises
from pydantic import BaseModel
from fastapi.testclient import TestClient
import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import NotConnectedToServerError
from labthings_fastapi.descriptors.property import (
    MismatchedTypeError,
    MissingTypeError,
    MissingDefaultError,
)


class TestThing(lt.Thing):
    boolprop = lt.ThingProperty[bool](
        initial_value=False, description="A boolean property"
    )
    stringprop = lt.ThingProperty[str](
        initial_value="foo", description="A string property"
    )

    _undoc = None

    @lt.thing_property
    def undoc(self) -> None:
        return self._undoc

    _float = 1.0

    @lt.thing_property
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
    Check the internal model (data type) of the ThingSetting descriptor is a BaseModel

    To send the data over HTTP LabThings-FastAPI uses Pydantic models to describe data
    types. Note that the model is not created until the property is assigned to a
    `Thing`, as it happens in `__set_name__` of the `ThingProperty` descriptor.
    """

    class BasicThing(lt.Thing):
        prop = lt.ThingProperty[bool](initial_value=False)

    assert issubclass(BasicThing.prop.model, BaseModel)


def exception_is_or_is_caused_by(err: Exception, cls: type[Exception]):
    return isinstance(err, cls) or isinstance(err.__cause__, cls)


def test_instantiation_with_type_and_model():
    """If a model is specified, we check it matches the inferred type."""

    class BasicThing(lt.Thing):
        prop = lt.ThingProperty[bool](model=bool, initial_value=False)

    with pytest.raises(Exception) as e:

        class InvalidThing(lt.Thing):
            prop = lt.ThingProperty[bool](model=int, initial_value=False)

    assert exception_is_or_is_caused_by(e.value, MismatchedTypeError)

    with pytest.raises(Exception) as e:

        class InvalidThing(lt.Thing):
            prop = lt.ThingProperty(model=bool, initial_value=False)

    assert exception_is_or_is_caused_by(e.value, MissingTypeError)


def test_missing_default():
    """Test that a default is required if no model is specified."""
    with pytest.raises(MissingDefaultError):

        class InvalidThing(lt.Thing):
            prop = lt.ThingProperty[bool]()


def test_annotation_on_class():
    """Test that a type annotation on the attribute is picked up."""

    class BasicThing(lt.Thing):
        prop: bool = lt.ThingProperty(initial_value=False)

    assert isinstance(BasicThing.prop, lt.ThingProperty)
    assert BasicThing.prop._value_type is bool


def test_overspecified_default():
    """Test that a default is not allowed if a getter is specified."""
    with pytest.raises(ValueError):

        class InvalidThing(lt.Thing):
            def get_prop(self) -> bool:
                return False

            prop = lt.ThingProperty[bool](initial_value=False, getter=get_prop)


def test_instantiation_with_model():
    class MyModel(BaseModel):
        a: int = 1
        b: float = 2.0

    class BasicThing(lt.Thing):
        prop = lt.ThingProperty[MyModel](initial_value=MyModel())

    assert BasicThing.prop.model is MyModel


def test_property_get_and_set():
    with TestClient(server.app) as client:
        test_str = "A silly test string"
        client.put("/thing/stringprop", json=test_str)
        after_value = client.get("/thing/stringprop")
        assert after_value.json() == test_str


def test_ThingProperty():
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
    """Test that an exception is raised if updating a ThingProperty
    without connecting the Thing to a running server with an event loop.
    """
    # This test may need to change, if we change the intended behaviour
    # Currently it should never be necessary to change properties from the
    # main thread, so we raise an error if you try to do so
    with raises(NotConnectedToServerError):
        thing.boolprop = False  # Can't call it until the event loop's running
