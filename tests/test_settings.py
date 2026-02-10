from threading import Thread
import tempfile
import json
from typing import Any
import pytest
import os

from pydantic import BaseModel, ValidationError
from fastapi.testclient import TestClient

import labthings_fastapi as lt
from labthings_fastapi.testing import create_thing_without_server


class MyModel(BaseModel):
    """A basic Model subclass.

    This is used to test that we can safely load/save settings that are
    `.BaseModel` instances. Prior to v0.0.14, these were loaded as dictionaries
    but they should now be correctly reinflated to the right class.
    """

    a: int
    b: str


class ThingWithSettings(lt.Thing):
    """A test `.Thing` with some settings and actions."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Initialize functional settings with default values
        self._floatsetting: float = 1.0
        self._localonlysetting = "Local-only default."

    boolsetting: bool = lt.setting(default=False)
    "A boolean setting."

    stringsetting: str = lt.setting(default="foo")
    "A string setting."

    dictsetting: dict = lt.setting(default_factory=lambda: {"a": 1, "b": 2})
    "A dictionary setting."

    modelsetting: MyModel = lt.setting(default_factory=lambda: MyModel(a=0, b="string"))
    "A setting that is a BaseModel."

    @lt.setting
    def floatsetting(self) -> float:
        """A float setting."""
        return self._floatsetting

    @floatsetting.setter
    def _set_floatsetting(self, value: float):
        self._floatsetting = value

    @lt.setting
    def localonlysetting(self) -> str:
        """A setting that is not writeable from HTTP clients or DirectThingClients.

        This setting has a setter, so may be written to from this Thing, or
        when settings are loaded. However, it's marked as read-only later, which
        means HTTP clients or DirectThingClient subclasses can't write to it.
        """
        return self._localonlysetting

    @localonlysetting.setter
    def _set_localonlysetting(self, value: str):
        self._localonlysetting = value

    localonlysetting.readonly = True

    localonly_boolsetting: bool = lt.setting(default=False, readonly=True)

    @lt.action
    def write_localonly_setting(self, value: str) -> None:
        """Change the value of the local-only setting.

        This is allowed - the setting is only read-only for code running
        over HTTP or via a DirectThingClient. By using this action, we can
        check it's writeable for local code.
        """
        self.localonlysetting = value

    @lt.action
    def toggle_localonly_boolsetting(self) -> None:
        """Toggle the local-only bool setting.

        Settings with `readonly=True` are read-only for client code via HTTP
        or a DirectThingClient. This action checks they are still writeable
        from within the Thing.
        """
        self.localonly_boolsetting = not self.localonly_boolsetting

    @lt.action
    def toggle_boolsetting(self):
        self.boolsetting = not self.boolsetting

    @lt.action
    def toggle_boolsetting_from_thread(self):
        t = Thread(target=self.toggle_boolsetting)
        t.start()


def _get_setting_file(server: lt.ThingServer, name: str):
    """Find the location of the settings file for a given Thing on a server."""
    path = server.things[name]._thing_server_interface.settings_file_path
    return os.path.normpath(path)


def _settings_dict(
    boolsetting=False,
    floatsetting=1.0,
    stringsetting="foo",
    dictsetting=None,
    modelsetting=None,
    localonlysetting="Local-only default.",
    localonly_boolsetting=False,
):
    """Return the expected settings dictionary

    Parameters can be updated from default values
    """
    if dictsetting is None:
        dictsetting = {"a": 1, "b": 2}
    if modelsetting is None:
        modelsetting = {"a": 0, "b": "string"}
    return {
        "boolsetting": boolsetting,
        "floatsetting": floatsetting,
        "stringsetting": stringsetting,
        "dictsetting": dictsetting,
        "modelsetting": modelsetting,
        "localonlysetting": localonlysetting,
        "localonly_boolsetting": localonly_boolsetting,
    }


@pytest.fixture
def tempdir():
    """A temporary directory"""
    with tempfile.TemporaryDirectory() as tempdir:
        # Yield rather than return so that the temp directory isn't cleaned up
        # until after the test is run
        yield tempdir


def test_setting_available():
    """Check default settings are available before connecting to server"""
    thing = create_thing_without_server(ThingWithSettings)
    assert not thing.boolsetting
    assert thing.stringsetting == "foo"
    assert thing.floatsetting == 1.0
    assert thing.localonlysetting == "Local-only default."
    assert thing.dictsetting == {"a": 1, "b": 2}
    assert thing.modelsetting == MyModel(a=0, b="string")


def test_functional_settings_save(tempdir):
    """Check updated settings are saved to disk

    ``floatsetting`` is a functional setting, we should also test
    a `.DataSetting` for completeness.
    """
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app) as client:
        # We write a new value to the property with a PUT request
        r = client.put("/thing/floatsetting", json=2.0)
        # A 201 return code means the operation succeeded (i.e.
        # the property was written to)
        assert r.status_code == 201
        # After successfully writing to the setting, it should
        # have created a settings file.
        assert os.path.isfile(setting_file)
        # We check the value with a GET request
        r = client.get("/thing/floatsetting")
        assert r.json() == 2.0
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(floatsetting=2.0)


def test_data_settings_save(tempdir):
    """Check updated settings are saved to disk

    This uses ``intsetting`` which is a `.DataSetting` so it tests
    a different code path to the functional setting above."""
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    # The settings file should not be created yet - it's created the
    # first time we write to a setting.
    assert not os.path.isfile(setting_file)
    with TestClient(server.app) as client:
        # Change the value using a PUT request
        r = client.put("/thing/boolsetting", json=True)
        # Check the value was written successfully (201 response code)
        assert r.status_code == 201
        # Check the value is what we expect
        r = client.get("/thing/boolsetting")
        assert r.json() is True
        # After successfully writing to the setting, it should
        # have created a settings file.
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(boolsetting=True)


def test_settings_dict_save(tempdir):
    """Check settings are saved if the dict is updated in full"""
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    thing = server.things["thing"]
    assert isinstance(thing, ThingWithSettings)
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app):
        thing.dictsetting = {"c": 3}
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(dictsetting={"c": 3})


def test_settings_dict_internal_update(tempdir):
    """Confirm settings are not saved if the internal value of a dictionary is updated

    This behaviour is not ideal, but it is documented. If the behaviour is updated
    then the documentation should be updated and this test removed
    """
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    thing = server.things["thing"]
    assert isinstance(thing, ThingWithSettings)
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app):
        thing.dictsetting["a"] = 4
        # As only an internal member of the dictornary was set, the saving was not
        # triggered.
        assert not os.path.isfile(setting_file)


def test_settings_load(tempdir):
    """Check settings can be loaded from disk when added to server"""
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    del server
    setting_json = json.dumps(_settings_dict(floatsetting=3.0, stringsetting="bar"))
    # Create setting file
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)
    # Add thing to server and check new settings are loaded
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    thing = server.things["thing"]
    assert isinstance(thing, ThingWithSettings)
    assert not thing.boolsetting
    assert thing.stringsetting == "bar"
    assert thing.floatsetting == 3.0


def test_load_extra_settings(caplog, tempdir):
    """Load from setting file. Extra setting in file should create a warning."""
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    del server
    setting_dict = _settings_dict(floatsetting=3.0, stringsetting="bar")
    setting_dict["extra_setting"] = 33.33
    setting_json = json.dumps(setting_dict)
    # Create setting file
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        # Create the server with the Thing added.
        _ = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)


def test_try_loading_corrupt_settings(tempdir, caplog):
    """Load from setting file. Extra setting in file should create a warning."""
    # Create the server once, so we can get the settings path
    server = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
    setting_file = _get_setting_file(server, "thing")
    del server

    # Construct a broken settings file
    setting_dict = _settings_dict(floatsetting=3.0, stringsetting="bar")
    setting_json = json.dumps(setting_dict)
    # Cut the start off the json to so it can't be decoded.
    setting_json = setting_json[3:]
    # Create setting file
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)

    # Recreate the server and check for the error
    with pytest.raises(ValidationError, match="Invalid JSON"):
        # Add thing to server
        _ = lt.ThingServer({"thing": ThingWithSettings}, settings_folder=tempdir)
