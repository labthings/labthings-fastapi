"""Test `lt.property` and its associated classes.

This is a new test module, intended to test individual bits of code,
rather than check the whole property mechanism at once. This should
mean this module is more bottom-up than the old
`test_properties.py`. Currently, both are part of the test suite,
as it's helpful to take both approaches.

This module currently focuses on checking the top level functions,
in particular checking `lt.property` and `lt.setting` work in the
same way.
"""

import fastapi
from fastapi.testclient import TestClient
import pydantic
import pytest
from labthings_fastapi import properties
from labthings_fastapi.properties import (
    BaseProperty,
    DataProperty,
    FunctionalProperty,
    MissingDefaultError,
    OverspecifiedDefaultError,
    default_factory_from_arguments,
)
from labthings_fastapi.base_descriptor import DescriptorAddedToClassTwiceError
from labthings_fastapi.exceptions import MissingTypeError, NotConnectedToServerError
import labthings_fastapi as lt
from .utilities import raises_or_is_caused_by


def test_default_factory_from_arguments():
    """Check the function that implements default/default_factory behaves correctly.

    It should always return a function that
    returns a default value, and should error if both arguments
    are provided, or if none are provided.
    """
    # Check for an error with no arguments
    with pytest.raises(MissingDefaultError):
        default_factory_from_arguments()

    # Check for an error with both arguments
    with pytest.raises(OverspecifiedDefaultError):
        default_factory_from_arguments([], list)

    # Check a factory is passed unchanged
    assert default_factory_from_arguments(..., list) is list

    # Check a value is wrapped in a factory
    factory = default_factory_from_arguments(True, None)
    assert factory() is True

    # Check there's an error if our default factory isn't callable
    with pytest.raises(MissingDefaultError):
        default_factory_from_arguments(default_factory=False)

    # Check None works as a default value
    factory = default_factory_from_arguments(default=None)
    assert factory() is None


class ArgCapturer:
    """A class that remembers its init arguments."""

    def __init__(self, *args, **kwargs):
        """Store arguments for later inspection."""
        self.args = args
        self.kwargs = kwargs


def mock_and_capture_args(monkeypatch, target, name):
    """Replace a class with an ArgCapturer

    A dynamically created subclass will be swapped in for the
    specified class, allowing its arguments to be checked.

    :param monkeypatch: the pytest fixture.
    :param target: the module where the class is defined.
    :param name: the class name.
    """
    MockClass = type(
        name,
        (ArgCapturer,),
        {},
    )
    monkeypatch.setattr(target, name, MockClass)


@pytest.mark.parametrize("func", [lt.property, lt.setting])
def test_toplevel_function(monkeypatch, func):
    """Test the various ways in which `lt.property` or `lt.setting` may be invoked.

    This test is parametrized, so `func` will be either `lt.property` or `lt.setting`.
    We then look up the corresponding descriptor classes.

    It's unfortunate that the body of this test is a bit generic, but as both
    functions should work identically, it's worth ensuring they are tested the same.

    This is intended only to test that `func` invokes the classes correctly,
    so they are mocked.
    """
    # Mock DataProperty,FunctionalProperty or the equivalent for settings
    # suffix will be "Property" or "Setting"
    suffix = func.__name__.capitalize()
    mock_and_capture_args(monkeypatch, properties, f"Data{suffix}")
    mock_and_capture_args(monkeypatch, properties, f"Functional{suffix}")
    DataClass = getattr(properties, f"Data{suffix}")
    FunctionalClass = getattr(properties, f"Functional{suffix}")

    def getter(self) -> str:
        return "test"

    # This is equivalent to use as a decorator
    prop = func(getter)
    # The decorator should instantiate a FunctionalProperty/FunctionalSetting
    assert isinstance(prop, FunctionalClass)
    assert prop.args == ()
    assert prop.kwargs == {"fget": getter}

    # When instantiated with a default, we make a
    # DataProperty/DataSetting. Note that we convert the default
    # to a datafactory using `default_factory_from_arguments`
    # so the class gets a default factory.`
    prop = func(default=0)
    assert isinstance(prop, DataClass)
    assert prop.args == ()
    assert prop.kwargs["default_factory"]() == 0
    assert prop.kwargs["readonly"] is False
    assert prop.kwargs["constraints"] == {}
    assert len(prop.kwargs) == 3

    # The same thing should happen when we use a factory,
    # except it should pass through the factory function unchanged.
    prop = func(default_factory=list)
    assert isinstance(prop, DataClass)
    assert prop.args == ()
    assert prop.kwargs["default_factory"] is list
    assert prop.kwargs["readonly"] is False
    assert prop.kwargs["constraints"] == {}
    assert len(prop.kwargs) == 3

    # The positional argument is the setter, so `None` is not valid
    # and probably means someone forgot to add `default=`.
    with pytest.raises(MissingDefaultError):
        func(None)

    # Calling with no arguments is also not valid and raises an error
    with pytest.raises(MissingDefaultError):
        func()

    # If more than one default is specified, we should raise an error.
    with pytest.raises(OverspecifiedDefaultError):
        func(default=[], default_factory=list)
    with pytest.raises(OverspecifiedDefaultError):
        func(getter, default=[])
    with pytest.raises(OverspecifiedDefaultError):
        func(getter, default_factory=list)


def test_baseproperty_type_and_model():
    """Test type functionality in BaseProperty

    This checks baseproperty correctly wraps plain types in a
    `pydantic.RootModel`.
    """

    with raises_or_is_caused_by(MissingTypeError):

        class Example:
            prop = BaseProperty()

    class Example:
        prop: "str | None" = BaseProperty()

    assert isinstance(None, Example.prop.value_type)
    assert isinstance("test", Example.prop.value_type)
    assert str(Example.prop.value_type) == "str | None"
    assert issubclass(Example.prop.model, pydantic.RootModel)
    assert str(Example.prop.model.model_fields["root"].annotation) == "str | None"
    testmodel = Example.prop.value_to_model("test")
    assert isinstance(testmodel, pydantic.RootModel)
    assert testmodel.root == "test"
    nonemodel = Example.prop.value_to_model(None)
    assert isinstance(nonemodel, pydantic.RootModel)
    assert nonemodel.root is None


def test_baseproperty_type_and_model_pydantic():
    """Test type functionality in BaseProperty

    This checks baseproperty behaves correctly when its
    type is a BaseModel instance.
    """

    class MyModel(pydantic.BaseModel):
        foo: str
        bar: int

    class Example:
        prop: MyModel = BaseProperty()

    assert Example.prop.value_type is MyModel
    assert Example.prop.model is MyModel

    value = MyModel(foo="test", bar=42)
    assert isinstance(value, Example.prop.value_type)
    assert Example.prop.value_to_model(value) is value


def test_baseproperty_add_to_fastapi():
    """Check the method that adds the property to the HTTP API."""
    # Subclass to add __set__ (which is missing on BaseProperty as it's
    # implemented by subclasses).

    class MyProperty(BaseProperty):
        def __set__(self, obj, val):
            pass

    class Example:
        prop = MyProperty()
        """A docstring with a title.
        
        A docstring body.
        """
        prop._type = str | None

        # Add a path attribute, so we can use Example as a mock Thing.
        path = "/example/"

    # Make a FastAPI app and retrieve the OpenAPI document
    app = fastapi.FastAPI()
    Example.prop.add_to_fastapi(app, Example())
    with TestClient(app) as tc:
        r = tc.get("/openapi.json")
        assert r.status_code == 200
        openapi = r.json()

    # Check the property appears at the expected place
    entry = openapi["paths"]["/example/prop"]
    # Check it declares the right methods
    assert set(entry.keys()) == {"get", "put"}


def test_baseproperty_set_error():
    """Check `.Baseproperty.__set__` raises an error and is overridden."""
    assert DataProperty.__get__ is BaseProperty.__get__
    assert DataProperty.__set__ is not BaseProperty.__set__
    assert FunctionalProperty.__set__ is not BaseProperty.__set__

    class Example:
        bp: int = BaseProperty()

    example = Example()
    with pytest.raises(NotImplementedError):
        example.bp = 0


def test_decorator_exception():
    r"""Check decorators work as expected when the setter has a different name.

    This is done to satisfy ``mypy`` and more information is in the
    documentation for `.property`\ , `.DescriptorAddedToClassTwiceError`
    and `.FunctionalProperty.__set_name__`\ .
    """
    # The exception should be specific - a simple double assignment is
    # still an error
    with raises_or_is_caused_by(DescriptorAddedToClassTwiceError):

        class BadExample:
            """A class with a wrongly reused descriptor."""

            prop1: int = lt.property(default=0)
            prop2: int = prop1

    # The example below should be exempted from the rule, i.e. no error
    class Example:
        @lt.property
        def prop(self) -> bool:
            """An example getter."""

        @prop.setter
        def _set_prop(self, val: bool) -> None:
            """A setter named differently."""
            pass

    assert isinstance(Example.prop, FunctionalProperty)
    assert Example.prop.name == "prop"
    assert not isinstance(Example._set_prop, FunctionalProperty)
    assert callable(Example._set_prop)


def test_premature_api_and_affordance(mocker):
    """Check the right error is raised if we add to API without a path."""

    class Example:
        path = None  # this is supplied by `lt.Thing` but we're not subclassing.

        @lt.property
        def prop(self) -> bool:
            """An example getter."""
            return True

    example = Example()

    with pytest.raises(NotConnectedToServerError):
        Example.prop.add_to_fastapi(mocker.Mock(), example)
    with pytest.raises(NotConnectedToServerError):
        Example.prop.property_affordance(example, None)
