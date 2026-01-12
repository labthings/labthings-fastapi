from dataclasses import dataclass
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any

from annotated_types import Ge, Le, Gt, Lt, MultipleOf, MinLen, MaxLen
from pydantic import BaseModel, RootModel, ValidationError
from fastapi.testclient import TestClient
import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import (
    ServerNotRunningError,
    UnsupportedConstraintError,
)
from labthings_fastapi.properties import BaseProperty
from .temp_client import poll_task


class PropertyTestThing(lt.Thing):
    """A Thing with various properties for testing."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._constrained_functional_int = 0
        self._constrained_functional_str_setting = "ddd"

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
    def _set_floatprop(self, value: float):
        self._float = value

    @lt.action
    def toggle_boolprop(self):
        self.boolprop = not self.boolprop

    @lt.action
    def toggle_boolprop_from_thread(self):
        """Toggle boolprop from a new threading.Thread.

        This checks we can still toggle the property from a thread
        that definitely isn't a worker thread created by FastAPI.
        """
        t = Thread(target=self.toggle_boolprop)
        t.start()
        # Ensure the thread has finished before the action completes:
        t.join()

    constrained_int: int = lt.property(default=5, ge=0, le=10, multiple_of=2)
    "An integer property with constraints"

    constrained_float: float = lt.property(default=5, gt=0, lt=10, allow_inf_nan=False)
    "A float property with constraints"

    constrained_str: str = lt.property(
        default="hello", min_length=3, max_length=10, pattern="^[a-z]+$"
    )
    "A string property with constraints"

    constrained_int_setting: int = lt.setting(default=5, ge=0, le=10, multiple_of=2)
    "An integer setting with constraints"

    @lt.property
    def constrained_functional_int(self) -> int:
        return self._constrained_functional_int

    @constrained_functional_int.setter
    def _set_constrained_functional_int(self, value: int):
        self._constrained_functional_int = value

    constrained_functional_int.constraints = {"ge": 0, "le": 10}

    @lt.setting
    def constrained_functional_str_setting(self) -> str:
        return self._constrained_functional_str_setting

    @constrained_functional_str_setting.setter
    def _set_constrained_functional_str_setting(self, value: str):
        self._constrained_functional_str_setting = value

    constrained_functional_str_setting.constraints = {
        "min_length": 3,
        "max_length": 10,
        "pattern": "^d+$",
    }


@dataclass
class ConstrainedPropInfo:
    name: str
    prop: BaseProperty
    value_type: type
    constraints: list[Any]
    valid_values: list[Any]
    invalid_values: list[Any]
    jsonschema_constraints: dict[str, Any]


CONSTRAINED_PROPS = [
    ConstrainedPropInfo(
        name="constrained_int",
        prop=PropertyTestThing.constrained_int,
        value_type=int,
        constraints=[Ge(0), Le(10), MultipleOf(2)],
        valid_values=[0, 2, 4, 6, 8, 10],
        invalid_values=[-2, 11, 3],
        jsonschema_constraints={"minimum": 0, "maximum": 10, "multipleOf": 2},
    ),
    ConstrainedPropInfo(
        name="constrained_float",
        prop=PropertyTestThing.constrained_float,
        value_type=float,
        constraints=[Gt(0), Lt(10)],
        valid_values=[0.1, 5.0, 9.9],
        invalid_values=[0.0, 10.0, -1.0, float("inf")],
        jsonschema_constraints={"exclusiveMinimum": 0.0, "exclusiveMaximum": 10.0},
    ),
    ConstrainedPropInfo(  # This checks "inf" is OK by default.
        name="floatprop",
        prop=PropertyTestThing.floatprop,
        value_type=float,
        constraints=[],
        valid_values=[-1.0, 0.0, 1.0, float("inf"), float("-inf"), float("nan")],
        invalid_values=[],
        jsonschema_constraints={},
    ),
    ConstrainedPropInfo(
        name="constrained_str",
        prop=PropertyTestThing.constrained_str,
        value_type=str,
        constraints=[MinLen(3), MaxLen(10)],
        valid_values=["abc", "ddddd", "tencharsaa"],
        invalid_values=["d", "ab", "verylongstring", "Invalid1"],
        jsonschema_constraints={"minLength": 3, "maxLength": 10, "pattern": "^[a-z]+$"},
    ),
    ConstrainedPropInfo(
        name="constrained_int_setting",
        prop=PropertyTestThing.constrained_int_setting,
        value_type=int,
        constraints=[Ge(0), Le(10), MultipleOf(2)],
        valid_values=[0, 2, 4, 6, 8, 10],
        invalid_values=[-2, 11, 3],
        jsonschema_constraints={"minimum": 0, "maximum": 10, "multipleOf": 2},
    ),
    ConstrainedPropInfo(
        name="constrained_functional_int",
        prop=PropertyTestThing.constrained_functional_int,
        value_type=int,
        constraints=[Ge(0), Le(10)],
        valid_values=[0, 5, 10],
        invalid_values=[-1, 11],
        jsonschema_constraints={"minimum": 0, "maximum": 10},
    ),
    ConstrainedPropInfo(
        name="constrained_functional_str_setting",
        prop=PropertyTestThing.constrained_functional_str_setting,
        value_type=str,
        constraints=[MinLen(3), MaxLen(10)],
        valid_values=["ddd", "dddd"],
        invalid_values=["dd", "thisisaverylongstring", "abc"],
        jsonschema_constraints={"minLength": 3, "maxLength": 10, "pattern": "^d+$"},
    ),
]


@pytest.fixture
def server():
    with TemporaryDirectory() as dirpath:
        server = lt.ThingServer({"thing": PropertyTestThing}, settings_folder=dirpath)
        yield server


def test_types_are_found():
    """Check the correct type is determined for PropertyTestThing's properties.

    Note that the special case of types that are already BaseModel subclasses
    is tested in test_instantiation_with_model.
    """
    T = PropertyTestThing
    # BaseProperty.value_type should be the (Python) type of the property
    assert T.boolprop.value_type is bool
    assert T.stringprop.value_type is str
    assert T.undoc.value_type is Any
    assert T.floatprop.value_type is float
    # BaseProperty.model should wrap that type in a RootModel
    for name in ["boolprop", "stringprop", "undoc", "floatprop"]:
        p = getattr(T, name)
        # Check the returned model is a rootmodel
        assert issubclass(p.model, RootModel)
        # Check that it is wrapping the correct type
        assert p.model.model_fields["root"].annotation is p.value_type


def test_instantiation_with_type():
    """Check the property's type is correctly wrapped in a BaseModel.

    To send the data over HTTP LabThings-FastAPI uses Pydantic models to describe data
    types. If a property is defined using simple Python types, we need to wrap them
    in a `pydantic` model. The type is exposed as `.value_type` and the wrapped
    model as `.model`.
    """

    # `prop` will not work unless the property is assigned to a thing
    class Dummy(lt.Thing):
        prop: bool = lt.property(default=False)

        @lt.property
        def func_prop(self) -> bool:
            return False

    assert Dummy.prop.value_type is bool
    assert issubclass(Dummy.prop.model, BaseModel)
    assert Dummy.func_prop.value_type is bool
    assert issubclass(Dummy.func_prop.model, BaseModel)


def test_instantiation_with_model() -> None:
    """If a property's type is already a model, it should not be wrapped."""

    class MyModel(BaseModel):
        a: int = 1
        b: float = 2.0

    class Dummy:
        prop: MyModel = lt.property(default=MyModel())

        @lt.property
        def func_prop(self) -> MyModel:
            return MyModel()

    assert Dummy.prop.model is MyModel
    assert Dummy.prop.value_type is MyModel
    # Dummy.prop is typed as MyModel, but it's a descriptor

    assert Dummy.func_prop.model is MyModel
    assert Dummy.func_prop.value_type is MyModel


def test_property_get_and_set(server):
    """Use PUT and GET requests to check the property.

    PUT sets the value and GET retrieves it, so we use a PUT
    to set a known value, and check it comes back when we read
    it with a GET request.
    """
    with TestClient(server.app) as client:
        test_str = "A silly test string"
        # Write to the property:
        response = client.put("/thing/stringprop", json=test_str)
        # Check for a successful response code
        assert response.status_code == 201
        # Check it was written successfully
        after_value = client.get("/thing/stringprop")
        assert after_value.status_code == 200
        assert after_value.json() == test_str


def test_boolprop(server):
    """Test that the boolean property can be read and written.

    PUT requests write to the property, and GET reads it.
    """
    with TestClient(server.app) as client:
        r = client.get("/thing/boolprop")
        assert r.status_code == 200  # Successful read
        assert r.json() is False  # Known initial value
        r = client.put("/thing/boolprop", json=True)
        assert r.status_code == 201  # Successful write
        r = client.get("/thing/boolprop")
        assert r.status_code == 200  # Successful read
        assert r.json() is True


def test_decorator_with_no_annotation(server):
    """Test a property made with an un-annotated function."""
    with TestClient(server.app) as client:
        r = client.get("/thing/undoc")
        assert r.status_code == 200  # Read the property OK
        assert r.json() is None  # The return value was None
        r = client.put("/thing/undoc", json="foo")
        assert r.status_code == 405  # Read-only, so "method not allowed"


def test_readwrite_with_getter_and_setter(server):
    """Test floatprop can be read and written with a getter/setter."""
    with TestClient(server.app) as client:
        r = client.get("/thing/floatprop")
        assert r.status_code == 200  # Read the property OK
        assert r.json() == 1.0  # Got the expected value
        r = client.put("/thing/floatprop", json=2.0)
        assert r.status_code == 201  # Wrote to the property OK
        r = client.get("/thing/floatprop")
        assert r.status_code == 200  # Read the property OK
        assert r.json() == 2.0  # Got the value we wrote
        # We check here that writing an invalid value raises an error code:
        r = client.put("/thing/floatprop", json="foo")
        assert r.status_code == 422  # Unprocessable entity (wrong type)


def test_sync_action(server):
    """Check that we can change a property by invoking an action.

    This action doesn't start any extra threads.
    """
    with TestClient(server.app) as client:
        # Write to the property so it has a known value
        r = client.put("/thing/boolprop", json=False)
        assert r.status_code == 201  # successful write
        r = client.get("/thing/boolprop")  # Read it back
        assert r.status_code == 200  # successful read
        assert r.json() is False  # the value we wrote

        # Now, we invoke the action with a POST request
        r = client.post("/thing/toggle_boolprop", json={})
        assert r.status_code == 201  # Action started OK
        # In the future, an action that completes quickly
        # could return 200, which would indicate it has
        # already finished. Currently, we always return
        # 201 to say we started successfully - we need
        # to poll the task to check it's finished.
        poll_task(client, r.json())
        # Read the property after it's been toggled
        r = client.get("/thing/boolprop")
        assert r.status_code == 200
        assert r.json() is True


def test_setting_from_thread(server):
    """Repeat test_sync_action but toggle the property from a new thread.

    This checks there's nothing special about the action thread.
    """
    with TestClient(server.app) as client:
        # Reset boolprop to a known state
        r = client.put("/thing/boolprop", json=False)
        assert r.status_code == 201
        r = client.get("/thing/boolprop")
        assert r.status_code == 200
        assert r.json() is False
        r = client.post("/thing/toggle_boolprop_from_thread", json={})
        assert r.status_code == 201  # Action started OK
        poll_task(client, r.json())
        # Check the property changed.
        r = client.get("/thing/boolprop")
        assert r.status_code == 200
        assert r.json() is True


def test_setting_without_event_loop():
    """Test DataProperty raises an error if set without an event loop."""
    # This test may need to change, if we change the intended behaviour
    # Currently it should never be necessary to change properties from the
    # main thread, so we raise an error if you try to do so
    server = lt.ThingServer({"thing": PropertyTestThing})
    thing = server.things["thing"]
    assert isinstance(thing, PropertyTestThing)
    with pytest.raises(ServerNotRunningError):
        thing.boolprop = False  # Can't call it until the event loop's running


@pytest.mark.parametrize("prop_info", CONSTRAINED_PROPS)
def test_constrained_properties(prop_info):
    """Test that constraints on property values generate correct models."""
    prop = prop_info.prop
    assert prop.value_type is prop_info.value_type
    m = prop.model
    assert issubclass(m, RootModel)
    for ann in prop_info.constraints:
        assert any(meta == ann for meta in m.model_fields["root"].metadata)
    for valid in prop_info.valid_values:
        instance = m(root=valid)
        validated = instance.model_dump()
        assert validated == valid or validated is valid  # `is` for NaN
    for invalid in prop_info.invalid_values:
        with pytest.raises(ValidationError):
            _ = m(root=invalid)


def convert_inf_nan(value):
    """Replace `float(`inf)` and `float(-inf)` with strings."""
    if value == float("inf"):
        return "Infinity"
    elif value == float("-inf"):
        return "-Infinity"
    elif value != value:  # NaN check
        return "NaN"
    else:
        return value


@pytest.mark.parametrize("prop_info", CONSTRAINED_PROPS)
def test_constrained_properties_http(server, prop_info):
    """Test properties with constraints on their values.

    This tests that the constraints are enforced when setting
    the properties via HTTP PUT requests.

    It also checks that the constraints propagate to the JSONSchema.
    """
    with TestClient(server.app) as client:
        r = client.get("/thing/")
        r.raise_for_status()
        thing_description = r.json()
        properties = thing_description["properties"]

        for valid in prop_info.valid_values:
            r = client.put(f"/thing/{prop_info.name}", json=convert_inf_nan(valid))
            err = f"Failed to set {prop_info.name}={valid}, {r.json()}"
            assert r.status_code == 201, err  # 201 means it was set successfully
        for invalid in prop_info.invalid_values:
            r = client.put(f"/thing/{prop_info.name}", json=convert_inf_nan(invalid))
            assert r.status_code == 422  # Unprocessable entity - invalid value
        property = properties[prop_info.name]
        for key, value in prop_info.jsonschema_constraints.items():
            assert property[key] == value


def test_bad_property_constraints():
    """Test that bad constraints raise errors at definition time."""

    class BadConstraintThing(lt.Thing):
        bad_prop: int = lt.property(default=0, allow_inf_nan=False)

    # Some constraints cause errors when the model is built. So far
    # I believe only allow_inf_nan on int does this.
    with pytest.raises(UnsupportedConstraintError):
        _ = BadConstraintThing.bad_prop.model

    # Other bad constraints raise errors when the property is created.
    # This should happen for any argument not in CONSTRAINT_ARGS
    with pytest.raises(UnsupportedConstraintError):

        class AnotherBadConstraintThing(lt.Thing):
            another_bad_prop: str = lt.property(default="foo", bad_constraint=2)

    # Some inappropriate constraints (e.g. multiple_of on str) are passed through
    # as metadata if used on the wrong type. We don't currently raise errors
    # for these.
