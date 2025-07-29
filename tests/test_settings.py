from threading import Thread
import tempfile
import json
import pytest
import os
import logging

from fastapi.testclient import TestClient

import labthings_fastapi as lt


class TestThing(lt.Thing):
    """A test `.Thing` with some settings and actions."""

    def __init__(self) -> None:
        super().__init__()
        # Initialize functional settings with default values
        self._floatsetting: float = 1.0

    boolsetting: bool = lt.setting(default=False)
    "A boolean setting"

    stringsetting: str = lt.setting(default="foo")
    "A string setting"

    dictsetting: dict = lt.setting(default_factory=lambda: {"a": 1, "b": 2})
    "A dictionary setting"

    @lt.setting
    def floatsetting(self) -> float:
        """A float setting."""
        return self._floatsetting

    @floatsetting.setter
    def floatsetting(self, value: float):
        self._floatsetting = value

    @lt.setting
    def readonlysetting(self) -> str:
        """A read-only setting."""
        return "This is read-only"

    @readonlysetting.setter
    def readonlysetting(self, value: str):
        pass

    readonlysetting.readonly = True

    @lt.thing_action
    def toggle_boolsetting(self):
        self.boolsetting = not self.boolsetting

    @lt.thing_action
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
        "readonlysetting": "This is read-only",
    }


@pytest.fixture
def thing():
    return TestThing()


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tempdir:
        # Yield server rather than return so that the temp directory isn't cleaned up
        # until after the test is run
        yield lt.ThingServer(settings_folder=tempdir)


def test_setting_available(thing):
    """Check default settings are available before connecting to server"""
    assert not thing.boolsetting
    assert thing.stringsetting == "foo"
    assert thing.floatsetting == 1.0
    assert thing.readonlysetting == "This is read-only"


def test_functional_settings_save(thing, server):
    """Check updated settings are saved to disk

    ``floatsetting`` is a functional setting, we should also test
    a `.DataSetting` for completeness."""
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


def test_data_settings_save(thing, server):
    """Check updated settings are saved to disk

    This uses ``intsetting`` which is a `.DataSetting` so it tests
    a different code path to the functional setting above."""
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing(thing, "/thing")
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app) as client:
        r = client.put("/thing/boolsetting", json=True)
        assert r.status_code == 201
        r = client.get("/thing/boolsetting")
        assert r.json() is True
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(boolsetting=True)


def test_readonly_setting(thing, server):
    """Check read-only settings cannot be set remotely."""
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing(thing, "/thing")
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app) as client:
        # Check we can read it over HTTP
        r = client.get("/thing/readonlysetting")
        assert r.json() == "This is read-only"
        assert r.status_code == 200
        # Attempt to set read-only setting
        r = client.put("/thing/readonlysetting", json="new value")
        assert r.status_code == 405
        assert not os.path.isfile(setting_file)  # No file created


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
