from threading import Thread
import tempfile
import json
import pytest
import os
import logging

from fastapi.testclient import TestClient

from labthings_fastapi.descriptors import ThingSetting
from labthings_fastapi.decorators import thing_setting, thing_action
from labthings_fastapi.thing import Thing
from labthings_fastapi.server import ThingServer


class TestThing(Thing):
    boolsetting = ThingSetting(bool, False, description="A boolean setting")
    stringsetting = ThingSetting(str, "foo", description="A string setting")
    dictsetting = ThingSetting(
        dict, {"a": 1, "b": 2}, description="A dictionary setting"
    )

    _float = 1.0

    @thing_setting
    def floatsetting(self) -> float:
        return self._float

    @floatsetting.setter
    def floatsetting(self, value: float):
        self._float = value

    @thing_action
    def toggle_boolsetting(self):
        self.boolsetting = not self.boolsetting

    @thing_action
    def toggle_boolsetting_from_thread(self):
        t = Thread(target=self.toggle_boolsetting)
        t.start()


def _get_setting_file(server, thingpath):
    path = os.path.join(server.settings_folder, thingpath.lstrip("/"), "settings.json")
    return os.path.normpath(path)


def _settings_dict(
    boolsetting=False, floatsetting=1.0, stringsetting="foo", dictsetting=None
):
    """Return the expected settings dictionary

    Parameters can be updated from default values
    """
    if dictsetting is None:
        dictsetting = {"a": 1, "b": 2}
    return {
        "boolsetting": boolsetting,
        "floatsetting": floatsetting,
        "stringsetting": stringsetting,
        "dictsetting": dictsetting,
    }


@pytest.fixture
def thing():
    return TestThing()


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tempdir:
        # Yield server rather than return so that the temp directory isn't cleaned up
        # until after the test is run
        yield ThingServer(settings_folder=tempdir)


def test_setting_available(thing):
    """Check default settings are available before connecting to server"""
    assert not thing.boolsetting
    assert thing.stringsetting == "foo"
    assert thing.floatsetting == 1.0


def test_settings_save(thing, server):
    """Check updated settings are saved to disk"""
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing(thing, "/thing")
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app) as client:
        r = client.put("/thing/floatsetting", json=2.0)
        assert r.status_code == 201
        r = client.get("/thing/floatsetting")
        assert r.json() == 2.0
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(floatsetting=2.0)


def test_settings_dict_save(thing, server):
    """Check settings are saved if the dict is updated in full"""
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing(thing, "/thing")
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app):
        thing.dictsetting = {"c": 3}
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(dictsetting={"c": 3})


def test_settings_dict_internal_update(thing, server):
    """Confirm settings are not saved if the internal value of a dictionary is updated

    This behaviour is not ideal, but it is documented. If the behaviour is updated
    then the documentation should be updated and this test removed
    """
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing(thing, "/thing")
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app):
        thing.dictsetting["a"] = 4
        # As only an internal member of the dictornary was set, the saving was not
        # triggered.
        assert not os.path.isfile(setting_file)


def test_settings_load(thing, server):
    """Check settings can be loaded from disk when added to server"""
    setting_file = _get_setting_file(server, "/thing")
    setting_json = json.dumps(_settings_dict(floatsetting=3.0, stringsetting="bar"))
    # Create setting file
    os.makedirs(os.path.dirname(setting_file))
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)
    # Add thing to server and check new settings are loaded
    server.add_thing(thing, "/thing")
    assert not thing.boolsetting
    assert thing.stringsetting == "bar"
    assert thing.floatsetting == 3.0


def test_load_extra_settings(thing, server, caplog):
    """Load from setting file. Extra setting in file should create a warning."""
    setting_file = _get_setting_file(server, "/thing")
    setting_dict = _settings_dict(floatsetting=3.0, stringsetting="bar")
    setting_dict["extra_setting"] = 33.33
    setting_json = json.dumps(setting_dict)
    # Create setting file
    os.makedirs(os.path.dirname(setting_file))
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)

    with caplog.at_level(logging.WARNING):
        # Add thing to server
        server.add_thing(thing, "/thing")
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].name == "labthings_fastapi.thing"

    # Check other settings are loaded as expected
    assert not thing.boolsetting
    assert thing.stringsetting == "bar"
    assert thing.floatsetting == 3.0


def test_try_loading_corrupt_settings(thing, server, caplog):
    """Load from setting file. Extra setting in file should create a warning."""
    setting_file = _get_setting_file(server, "/thing")
    setting_dict = _settings_dict(floatsetting=3.0, stringsetting="bar")
    setting_json = json.dumps(setting_dict)
    # Cut the start off the json to so it can't be decoded.
    setting_json = setting_json[3:]
    # Create setting file
    os.makedirs(os.path.dirname(setting_file))
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)

    with caplog.at_level(logging.WARNING):
        # Add thing to server
        server.add_thing(thing, "/thing")
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].name == "labthings_fastapi.thing"

    # Check default settings are loaded
    assert not thing.boolsetting
    assert thing.stringsetting == "foo"
    assert thing.floatsetting == 1.0
