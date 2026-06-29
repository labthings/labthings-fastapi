r"""Test code for `.server.config_model`\ ."""

import pytest
from pydantic import ValidationError

import labthings_fastapi.example_things
from labthings_fastapi.example_things import MyThing
from labthings_fastapi.server.config_model import (
    ThingConfig,
    ThingImportFailure,
    ThingServerConfig,
)


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

    with pytest.raises(ThingImportFailure, match="No module named 'missing'"):
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
    "things",
    "cls",
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

    # Check some good prefixes
    for prefix in ["", "/api", "/api/v2", "/api-v2"]:
        config = ThingServerConfig(things={}, api_prefix=prefix)
        assert config.api_prefix == prefix

    # Check some bad prefixes
    for prefix in ["api", "/api/", "api/", "api/v2", "/badchars!"]:
        with pytest.raises(ValidationError):
            ThingServerConfig(things={}, api_prefix=prefix)


@pytest.mark.parametrize(
    ("import_string", "message"),
    [
        (
            # The error message should refer to the missing module - i.e.
            # `missing` rather than `missing.module`\ .
            "missing.module:object",
            "No module named 'missing'",
        ),
        (
            # Check that, if a module has a broken import, the error refers
            # to that missing import and doesn't suggest the target module
            # is missing. This was an upstream bug, fixed in Pydantic 2.13
            "tests.unimportable.missing_import:object",
            "No module named 'missing_module'",
        ),
        (
            # RuntimeError in the module should get reported with a single error
            "tests.unimportable.runtimeerror:SomeClass",
            r"\[RuntimeError\] This module should not be importable!",
        ),
        (
            # ValueError in the module should be wrapped in ThingImportFailure
            "tests.unimportable.valueerror:SomeClass",
            r"\[ValueError\] This module should not be importable due to ValueError!",
        ),
        (
            "tests.unimportable.missing:SomeClass",  # This module does not exist
            "No module named 'tests.unimportable.missing'",
        ),
        (
            "tests.unimportable:MissingClass",  # Module exists, class does not.
            "cannot import name 'MissingClass' from 'tests.unimportable'",
        ),
    ],
)
def test_unimportable_modules(import_string: str, message: str):
    """Test that unimportable modules raise errors as expected."""

    with pytest.raises(ThingImportFailure, match=message):
        # If a module is missing, the error should make that clear.
        # Note that the error message changed with Pydantic 2.13.
        ThingConfig(cls=import_string)


def test_defaults():
    """Check the default values.

    This test is intended as a double-check so that any change in default
    values must be made both here and in the config model.
    """
    config = ThingServerConfig(things={})
    assert config.things == {}
    assert config.api_prefix == ""
    assert config.application_config is None
    assert config.enable_global_lock is False
    assert config.global_lock_log_level == "INFO"
    assert config.settings_folder is None
    # Check there aren't any fields missing from this test
    assert len(ThingServerConfig.model_fields) == 6
