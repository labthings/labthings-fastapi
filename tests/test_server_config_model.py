r"""Test code for `.server.config_model`\ ."""

from pydantic import ValidationError
import pytest
from labthings_fastapi.server.config_model import ThingConfig, ThingServerConfig
import labthings_fastapi.example_things
from labthings_fastapi.example_things import MyThing


def test_ThingConfig():
    """Test the ThingConfig model loads classes as expected."""
    # We should be able to create a valid config with just a class
    direct = ThingConfig(cls=labthings_fastapi.example_things.MyThing)
    # Equivalently, we should be able to pass a string
    fromstr = ThingConfig(cls="labthings_fastapi.example_things:MyThing")
    assert direct.cls is MyThing
    assert fromstr.cls is MyThing
    # In the absence of supplied arguments, default factories should be used
    assert len(direct.args) == 0
    assert direct.kwargs == {}
    assert direct.thing_slots == {}

    with pytest.raises(ValidationError, match="No module named"):
        ThingConfig(cls="missing.module")


VALID_THING_CONFIGS = {
    "direct": MyThing,
    "string": "labthings_fastapi.example_things:MyThing",
    "model_d": ThingConfig(cls=MyThing),
    "model_s": ThingConfig(cls="labthings_fastapi.example_things:MyThing"),
    "dict_d": {"cls": MyThing},
    "dict_da": {"class": MyThing},
    "dict_s": {"cls": "labthings_fastapi.example_things:MyThing"},
    "dict_sa": {"class": "labthings_fastapi.example_things:MyThing"},
}


INVALID_THING_CONFIGS = [
    {},
    {"foo": "bar"},
    {"class": MyThing, "kwargs": 1},
    "missing.module:object",
    4,
    None,
    False,
]


VALID_THING_NAMES = [
    "my_thing",
    "MyThing",
    "Something",
    "f90785342",
    "1",
]

INVALID_THING_NAMES = [
    "",
    "spaces in name",
    "special * chars",
    False,
    1,
    "/",
    "thing/with/slashes",
    "trailingslash/",
    "/leadingslash",
]


def test_ThingServerConfig():
    """Check validation of the whole server config."""
    # Things should be able to be specified as a string, a class, or a ThingConfig
    config = ThingServerConfig(things=VALID_THING_CONFIGS)
    assert len(config.thing_configs) == 8
    for v in config.thing_configs.values():
        assert v.cls is MyThing

    # When we validate from a dict, the same options work
    config = ThingServerConfig.model_validate({"things": VALID_THING_CONFIGS})
    assert len(config.thing_configs) == 8
    for v in config.thing_configs.values():
        assert v.cls is MyThing

    # Check invalid configs are picked up
    for spec in INVALID_THING_CONFIGS:
        with pytest.raises(ValidationError):
            ThingServerConfig(things={"thing": spec})

    # Check valid names are allowed
    for name in VALID_THING_NAMES:
        sc = ThingServerConfig(things={name: MyThing})
        assert sc.thing_configs[name].cls is MyThing

    # Check bad names raise errors
    for name in INVALID_THING_NAMES:
        with pytest.raises(ValidationError):
            ThingServerConfig(things={name: MyThing})


def test_unimportable_module():
    """Test that unimportable modules raise errors as expected."""
    expected_message = "exception was raised when importing 'tests.unimportable"
    with pytest.raises(ValidationError, match=expected_message):
        # This checks RuntimErrors get reported with a single error
        ThingConfig(cls="tests.unimportable.runtimeerror:SomeClass")
    with pytest.raises(ValidationError, match=expected_message):
        # This checks ValueErrors get reported with a single error
        # rather than getting swallowed by a ValidationError
        ThingConfig(cls="tests.unimportable.valueerror:SomeClass")
    with pytest.raises(
        ValidationError,
        match="No module named 'tests.unimportable.missing'",
    ):
        # This checks normal ImportErrors get reported as usual
        ThingConfig(cls="tests.unimportable.missing:SomeClass")
    with pytest.raises(ValidationError, match="cannot import name 'MissingClass'"):
        # This checks normal ImportErrors get reported as usual
        ThingConfig(cls="tests.unimportable:MissingClass")
