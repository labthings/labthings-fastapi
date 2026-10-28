r"""Test the machinery behind `.Thing._class_settings`."""

import warnings

import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import (
    DefaultWillChangeWarning,
    InvalidClassSettingsError,
)
from labthings_fastapi.thing_class_settings import (
    get_class_settings,
    get_validate_properties_on_set,
    validate_thing_class_settings,
)


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({"validate_properties_on_set": True}, True),
        ({"validate_properties_on_set": False}, False),
        ({}, False),
    ],
)
def test_validate_settings(settings, expected):
    """Test validation with empty settings dict."""

    class TestThing(lt.Thing):
        _class_settings = settings

    # This should run, raise no errors, and leave settings unchanged.
    assert get_class_settings(TestThing) == settings
    validate_thing_class_settings(TestThing)
    assert TestThing._class_settings == settings
    assert get_validate_properties_on_set(TestThing) is expected


@pytest.mark.parametrize(
    "settings",
    [
        {"unknown_setting": True},  # invalid key
        {"validate_properties_on_set": "string"},  # wrong type
    ],
)
def test_invalid_settings(settings, mocker):
    """Test validation raises error with unknown keys.

    Note that `validate_thing_class_settings` is called by `Thing.__init_subclass__`
    and so we can't actually define a class with invalid settings.
    """

    with pytest.raises(InvalidClassSettingsError, match="TestThing._class_settings"):

        class TestThing(lt.Thing):
            _class_settings = settings

    # We can also test more directly if we mock the Thing.
    Stub = mocker.Mock()
    Stub._class_settings = settings
    Stub.__name__ = "Stub"
    with pytest.raises(InvalidClassSettingsError):
        validate_thing_class_settings(Stub)


def test_no_settings(mocker):
    """Test the settings are allowed to be unspecified and default to {}."""

    class TestThing(lt.Thing):
        pass

    class TestClass:
        pass

    MockClass = mocker.MagicMock()
    MockClass.__name__ = "MockClass"
    del MockClass._class_settings

    for cls in [TestThing, TestClass, MockClass]:
        assert get_class_settings(cls) == {}
        # This shouldn't error even if settings are missing. This
        # may occur with mixin classes, as __init_subclass__
        # won't be called.
        assert get_validate_properties_on_set(cls) is False

        validate_thing_class_settings(cls)
        assert get_validate_properties_on_set(cls) is False
        assert cls._class_settings == {}


def test_non_dictionary_settings(mocker):
    """Test we get a helpful error if the class settings has the wrong type."""
    MockClass = mocker.MagicMock()
    MockClass.__name__ = "MockClass"
    MockClass._class_settings = "settings"
    with pytest.raises(TypeError, match="`_class_settings` .* `dict`."):
        get_class_settings(MockClass)


def test_validate_raises_deprecation_warning_when_setting_not_specified():
    """Test that deprecation warning is raised for a missing value."""

    class TestThing(lt.Thing):
        _class_settings = {}

    with pytest.warns(DefaultWillChangeWarning):
        get_validate_properties_on_set(TestThing)


@pytest.mark.parametrize("value", [True, False])
def test_no_warning_when_setting_is_specified(value):
    """Test that no warning is raised when validate_properties_on_set is set."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # Convert warnings to errors

        class TestThing(lt.Thing):
            _class_settings = {"validate_properties_on_set": value}

        validate_thing_class_settings(TestThing)
