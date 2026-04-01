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

from dataclasses import dataclass
import json
from typing import Any

import fastapi
from fastapi.testclient import TestClient
import pydantic
import pytest
from labthings_fastapi import properties
from labthings_fastapi.feature_flags import FEATURE_FLAGS
from labthings_fastapi.properties import (
    BaseProperty,
    DataProperty,
    FunctionalProperty,
    MissingDefaultError,
    OverspecifiedDefaultError,
    default_factory_from_arguments,
)
from labthings_fastapi.base_descriptor import DescriptorAddedToClassTwiceError
from labthings_fastapi.exceptions import (
    FeatureNotAvailableError,
    MissingTypeError,
    NotBoundToInstanceError,
    NotConnectedToServerError,
    PropertyRedefinitionError,
)
import labthings_fastapi as lt
from labthings_fastapi.testing import create_thing_without_server
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
    documentation for `~lt.property`\ , `.DescriptorAddedToClassTwiceError`
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


def test_propertyinfo(mocker):
    """Test out the PropertyInfo class."""

    class MyModel(pydantic.BaseModel):
        a: int
        b: str

    class Example(lt.Thing):
        intprop: int = lt.property(default=0)
        """A normal, simple, integer property."""

        positive: int = lt.property(default=0, gt=0)
        """A positive integer property."""

        badprop: int = lt.property(default=1)
        """An integer property that I will break later."""

        tupleprop: tuple[int, str] = lt.property(default=(42, "the answer"))
        """A tuple property, to check subscripted generics work."""

        modelprop: MyModel = lt.property(default_factory=lambda: MyModel(a=1, b="two"))
        """A property typed as a model."""

        rootmodelprop: pydantic.RootModel[int | None] = lt.property(
            default_factory=lambda: pydantic.RootModel[int | None](root=None)
        )
        """A very verbosely defined optional integer.
        
        This tests a model that's also a subscripted generic.
        """

    # We will break `badprop` by setting its model to something that's
    # neither the type nor a rootmodel.
    badprop = Example.badprop
    assert isinstance(badprop, lt.DataProperty)

    class BadIntModel(pydantic.BaseModel):
        root: int

    badprop._model = BadIntModel

    example = create_thing_without_server(Example)

    # Set the property and check the three different ways we can get it
    example.properties["intprop"].set(15)
    assert example.intprop == 15  # Using the descriptor's __get__
    assert example.properties["intprop"].get() == 15  # Via the PropertyInfo object
    model = example.properties["intprop"].model_instance  # As a RootModel
    assert isinstance(model, pydantic.RootModel)
    assert model.root == 15

    # Check we can validate properly
    intprop = example.properties["intprop"]
    assert intprop.validate(15) == 15  # integers pass straight through
    assert intprop.validate(-15) == -15
    # A RootModel instance ought still to validate
    assert intprop.validate(intprop.model(root=42)) == 42
    # A wrong model won't, though.
    with pytest.raises(pydantic.ValidationError):
        intprop.validate(BadIntModel(root=42))

    # Check that a broken `_model` raises the right error
    # See above for where we manually set badprop._model to something that's
    # not a rootmodel.
    with FEATURE_FLAGS.set_temporarily(validate_properties_on_set=True):
        with pytest.raises(TypeError):
            example.badprop = 3  # Validation will fail here because of the bad model.
    with pytest.raises(TypeError):
        _ = example.properties["badprop"].model_instance
    with pytest.raises(TypeError):
        # The value is fine, but the model has been set to an invalid type.
        # This error shouldn't be seen in production.
        example.properties["badprop"].validate(0)

    # Check validation applies constraints
    positive = example.properties["positive"]
    assert positive.validate(42) == 42
    with pytest.raises(pydantic.ValidationError):
        positive.validate(0)

    # Check validation works for subscripted generics
    tupleprop = example.properties["tupleprop"]
    assert tupleprop.validate((1, "two")) == (1, "two")

    for val in [0, "str", ("str", 0)]:
        with pytest.raises(pydantic.ValidationError):
            tupleprop.validate(val)

    # Check validation for a model
    modelprop = example.properties["modelprop"]
    assert modelprop.validate(MyModel(a=3, b="four")) == MyModel(a=3, b="four")
    # Check that a valid model passes through unchanged: this should indicate that
    # we're not unnecessarily re-validating already-valid models.
    m = MyModel(a=3, b="four")
    assert modelprop.validate(m) is m
    assert modelprop.validate({"a": 5, "b": "six"}) == MyModel(a=5, b="six")
    for invalid in [{"c": 5}, (4, "f"), None]:
        with pytest.raises(pydantic.ValidationError):
            modelprop.validate(invalid)
    # Check that an invalid model doesn't get re-validated. This is intended behaviour:
    # it is another test that we're not unnecessarily re-validating a model that
    # should already have been validated when it was created.
    # Creating models with `model_construct` intentionally allows invalid models:
    # if this is used downstream, the downstream code should accept responsibility!
    bad_m = MyModel.model_construct(a="not an int", b=6)
    assert modelprop.validate(bad_m) is bad_m
    with pytest.raises(pydantic.ValidationError):
        # Check that passing the same data in as a dict fails validation.
        modelprop.validate(bad_m.model_dump())

    # Check again for an odd rootmodel
    rootmodelprop = example.properties["rootmodelprop"]
    m = rootmodelprop.validate(42)
    assert isinstance(m, pydantic.RootModel)
    assert m.root == 42
    assert m == pydantic.RootModel[int | None](root=42)
    assert rootmodelprop.validate(m) is m  # RootModel passes through
    assert rootmodelprop.validate(None).root is None
    for invalid in ["seven", {"root": None}, 14.5, pydantic.RootModel[int](root=0)]:
        with pytest.raises(pydantic.ValidationError):
            modelprop.validate(invalid)
        # Tty constructing a model with an invalid root value, skipping validation
        invalid_model = rootmodelprop.model.model_construct(invalid)
        # The RootModel gets re-validated, in contrast to the BaseModel above.
        with pytest.raises(pydantic.ValidationError):
            assert modelprop.validate(invalid_model) == invalid


def test_readonly_metadata():
    """Check read-only data propagates to the Thing Description."""

    class Example(lt.Thing):
        prop: int = lt.property(default=0)
        ro_property: int = lt.property(default=0, readonly=True)

        @lt.property
        def ro_functional_property(self) -> int:
            """This property should be read-only as there's no setter."""
            return 42

        @lt.property
        def ro_functional_property_with_setter(self) -> int:
            return 42

        @ro_functional_property_with_setter.setter
        def _set_ro_functional_property_with_setter(self, val: int) -> None:
            pass

        ro_functional_property_with_setter.readonly = True

        @lt.property
        def funcprop(self) -> int:
            return 42

        @funcprop.setter
        def _set_funcprop(self, val: int) -> None:
            pass

    example = create_thing_without_server(Example)

    td = example.thing_description()
    assert td.properties is not None  # This is mostly for type checking

    # Check read-write properties are not read-only
    for name in ["prop", "funcprop"]:
        assert td.properties[name].readOnly is False

    for name in [
        "ro_property",
        "ro_functional_property",
        "ro_functional_property_with_setter",
    ]:
        assert td.properties[name].readOnly is True


@dataclass
class PropertyDefaultInfo:
    name: str
    resettable: bool
    default: Any
    resets_to: Any = ...


DEFAULT_AND_RESET_PROPS = [
    PropertyDefaultInfo("intprop", True, 42, 42),
    PropertyDefaultInfo("listprop", True, ["a", "list"], ["a", "list"]),
    PropertyDefaultInfo("strprop", False, ...),
    PropertyDefaultInfo("tupleprop", False, (42, 42)),
    PropertyDefaultInfo("flistprop", True, [], []),
    PropertyDefaultInfo("resettable_strprop", True, ..., "Reset"),
    PropertyDefaultInfo("resettable_strprop_with_default", True, "Default", "Reset"),
]


@pytest.mark.parametrize("prop", DEFAULT_AND_RESET_PROPS)
def test_default_and_reset(prop: PropertyDefaultInfo):
    """Test retrieving property defaults, and resetting to default."""

    class Example(lt.Thing):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._flistprop = [0]
            self._resettable_strprop = "Hello World!"
            self._resettable_strprop_with_default = "Hello World!"

        intprop: int = lt.property(default=42)
        listprop: list[str] = lt.property(default_factory=lambda: ["a", "list"])

        @lt.property
        def strprop(self) -> str:
            """A functional property without resetter or default"""
            return "Hello World!"

        @lt.property
        def tupleprop(self) -> tuple[int, int]:
            """A functional property with a default but no setter."""
            return (42, 42)

        tupleprop.default = (42, 42)

        @lt.property
        def flistprop(self) -> list[int]:
            """A functional property with a default and a setter."""
            return self._listprop

        @flistprop.setter
        def _set_flistprop(self, value: list[int]) -> None:
            self._listprop = value

        flistprop.default_factory = list

        @lt.property
        def resettable_strprop(self) -> str:
            """A string property that may be reset, but has no default defined."""
            return self._resettable_strprop

        @resettable_strprop.resetter
        def _reset_resettable_strprop(self) -> None:
            self._resettable_strprop = "Reset"

        @lt.property
        def resettable_strprop_with_default(self) -> str:
            """A string property with a default, and a resetter."""
            return self._resettable_strprop_with_default

        @resettable_strprop_with_default.setter
        def _set_resettable_strprop_with_default(self, value: str):
            self._resettable_strprop_with_default = value

        @resettable_strprop_with_default.resetter
        def _reset_resettable_strprop_with_default(self):
            self._resettable_strprop_with_default = "Reset"

        resettable_strprop_with_default.default_factory = lambda: "Default"

    example = create_thing_without_server(Example)

    # Defaults should be available on classes and instances
    for thing in [example, Example]:
        # We should get expected values for defaults
        if prop.default is not ...:
            assert thing.properties[prop.name].default == prop.default
        else:
            with pytest.raises(FeatureNotAvailableError):
                _ = thing.properties[prop.name].default

    # Resetting to default isn't available on classes
    with pytest.raises(NotBoundToInstanceError):
        thing.properties[prop.name].reset()

    # Check the `resettable` property is correct
    for thing in [example, Example]:
        assert thing.properties[prop.name].is_resettable is prop.resettable

    # Check resetting either works as expected, or fails with the right error
    if prop.resettable:
        example.properties[prop.name].reset()
        assert getattr(example, prop.name) == prop.resets_to
    else:
        with pytest.raises(FeatureNotAvailableError):
            example.properties[prop.name].reset()

    # Check defaults show up in the Thing Description
    td = example.thing_description_dict()
    if prop.default is not ...:
        # The TD goes via JSON, so types may get changed
        default = json.loads(json.dumps(prop.default))
        assert td["properties"][prop.name]["default"] == default
    else:
        assert "default" not in td["properties"][prop.name]


def test_reading_default_and_factory():
    """Ensure reading the default/factory does what's expected.

    Note that this is **not** the same as Example.properties["prop"].default,
    which uses ``Example.prop.get_default()`` internally.

    This property really only exists for use during class definitions, and
    would be write-only if that wasn't confusing!
    """

    class Example(lt.Thing):
        @lt.property
        def prop(self) -> int:
            return 42

        @lt.property
        def prop_d(self) -> int:
            return 42

        prop_d.default = 42
        assert prop_d.default == 42
        assert prop_d.default_factory is not None
        assert prop_d.default_factory() == 42

        @lt.property
        def prop_df(self) -> int:
            return 42

        prop_df.default_factory = lambda: 42
        assert prop_df.default == 42
        assert prop_df.default_factory is not None
        assert prop_df.default_factory() == 42

    with pytest.raises(FeatureNotAvailableError):
        _ = Example.prop.default
    assert Example.prop.default_factory is None

    assert Example.prop_d.default == 42
    assert Example.prop_d.default_factory is not None
    assert Example.prop_d.default_factory() == 42

    assert Example.prop_df.default == 42
    assert Example.prop_df.default_factory is not None
    assert Example.prop_df.default_factory() == 42


def test_bad_reset_decorator():
    """Check that a resetter can't have the same name as the property."""

    with pytest.raises(PropertyRedefinitionError):

        class Example(lt.Thing):
            @lt.property
            def myprop(self) -> int:
                return 42

            @myprop.resetter
            def myprop(self) -> None:
                pass
