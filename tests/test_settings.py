from threading import Thread
import tempfile
import json
from typing import Any
import pytest
import os
import logging

from fastapi.testclient import TestClient

import labthings_fastapi as lt
from labthings_fastapi.thing_server_interface import create_thing_without_server
from .temp_client import poll_task


class ThingWithSettings(lt.Thing):
    """A test `.Thing` with some settings and actions."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Initialize functional settings with default values
        self._floatsetting: float = 1.0
        self._localonlysetting = "Local-only default."

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
    def localonlysetting(self) -> str:
        """A setting that is not writeable from HTTP clients or DirectThingClients.

        This setting has a setter, so may be written to from this Thing, or
        when settings are loaded. However, it's marked as read-only later, which
        means HTTP clients or DirectThingClient subclasses can't write to it.
        """
        return self._localonlysetting

    @localonlysetting.setter
    def localonlysetting(self, value: str):
        self._localonlysetting = value

    localonlysetting.readonly = True

    localonly_boolsetting: bool = lt.setting(default=False, readonly=True)

    @lt.thing_action
    def write_localonly_setting(self, value: str) -> None:
        """Change the value of the local-only setting.

        This is allowed - the setting is only read-only for code running
        over HTTP or via a DirectThingClient. By using this action, we can
        check it's writeable for local code.
        """
        self.localonlysetting = value

    @lt.thing_action
    def toggle_localonly_boolsetting(self) -> None:
        """Toggle the local-only bool setting.

        Settings with `readonly=True` are read-only for client code via HTTP
        or a DirectThingClient. This action checks they are still writeable
        from within the Thing.
        """
        self.localonly_boolsetting = not self.localonly_boolsetting

    @lt.thing_action
    def toggle_boolsetting(self):
        self.boolsetting = not self.boolsetting

    @lt.thing_action
    def toggle_boolsetting_from_thread(self):
        t = Thread(target=self.toggle_boolsetting)
        t.start()


ThingWithSettingsClientDep = lt.deps.direct_thing_client_dependency(
    ThingWithSettings, "thing"
)
ThingWithSettingsDep = lt.deps.raw_thing_dependency(ThingWithSettings)


class ClientThing(lt.Thing):
    """This Thing attempts to set read-only settings on ThingWithSettings.

    Read-only settings may not be set by DirectThingClient wrappers,
    which is what this class tests.
    """

    @lt.thing_action
    def set_localonlysetting(
        self,
        client: ThingWithSettingsClientDep,
        val: str,
    ):
        """Attempt to set a setting with a DirectThingClient."""
        client.localonlysetting = val

    @lt.thing_action
    def set_localonly_boolsetting(
        self,
        client: ThingWithSettingsClientDep,
        val: bool,
    ):
        """Attempt to set a setting with a DirectThingClient.

        This should fail with an error, as it's not writeable from a
        DirectThingClient.
        """
        client.localonly_boolsetting = val

    @lt.thing_action
    def directly_set_localonlysetting(
        self,
        test_thing: ThingWithSettingsDep,
        val: str,
    ):
        """Attempt to set a setting directly."""
        test_thing.localonlysetting = val

    @lt.thing_action
    def directly_set_localonly_boolsetting(
        self,
        test_thing: ThingWithSettingsDep,
        val: bool,
    ):
        """Attempt to set a setting directly.

        This should work, even though the setting is read-only from clients.
        Using a raw thing dependency bypasses that restriction.
        """
        test_thing.localonly_boolsetting = val


def _get_setting_file(server, thingpath):
    path = os.path.join(server.settings_folder, thingpath.lstrip("/"), "settings.json")
    return os.path.normpath(path)


def _settings_dict(
    boolsetting=False,
    floatsetting=1.0,
    stringsetting="foo",
    dictsetting=None,
    localonlysetting="Local-only default.",
    localonly_boolsetting=False,
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
        "localonlysetting": localonlysetting,
        "localonly_boolsetting": localonly_boolsetting,
    }


@pytest.fixture
def server():
    with tempfile.TemporaryDirectory() as tempdir:
        # Yield server rather than return so that the temp directory isn't cleaned up
        # until after the test is run
        yield lt.ThingServer(settings_folder=tempdir)


def test_setting_available():
    """Check default settings are available before connecting to server"""
    thing = create_thing_without_server(ThingWithSettings)
    assert not thing.boolsetting
    assert thing.stringsetting == "foo"
    assert thing.floatsetting == 1.0
    assert thing.localonlysetting == "Local-only default."
    assert thing.dictsetting == {"a": 1, "b": 2}


def test_functional_settings_save(server):
    """Check updated settings are saved to disk

    ``floatsetting`` is a functional setting, we should also test
    a `.DataSetting` for completeness."""
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing("thing", ThingWithSettings)
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app) as client:
        # We write a new value to the property with a PUT request
        r = client.put("/thing/floatsetting", json=2.0)
        # A 201 return code means the operation succeeded (i.e.
        # the property was written to)
        assert r.status_code == 201
        # We check the value with a GET request
        r = client.get("/thing/floatsetting")
        assert r.json() == 2.0
        # After successfully writing to the setting, it should
        # have created a settings file.
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(floatsetting=2.0)


def test_data_settings_save(server):
    """Check updated settings are saved to disk

    This uses ``intsetting`` which is a `.DataSetting` so it tests
    a different code path to the functional setting above."""
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing("thing", ThingWithSettings)
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


@pytest.mark.parametrize(
    ("endpoint", "value"),
    [
        ("localonlysetting", "Other value"),
        ("localonly_boolsetting", True),
    ],
)
@pytest.mark.parametrize(
    "method",
    ["http", "direct_thing_client", "direct"],
)
def test_readonly_setting(server, endpoint, value, method):
    """Check read-only functional settings cannot be set remotely.

    Functional settings must always have a setter, and will be
    writeable from within the Thing. However, they should not
    be settable remotely or via a DirectThingClient.

    This test is a bit complicated, but it checks both a
    `.FunctionalSetting` and a `.DataSetting` via all three
    methods: HTTP, DirectThingClient, and directly on the Thing.
    Only the last method should work.

    The test is parametrized so it will run 6 times, trying one
    block of code inside the ``with`` block each time.
    """
    setting_file = _get_setting_file(server, "/thing")
    server.add_thing("thing", ThingWithSettings)
    server.add_thing("client_thing", ClientThing)
    # No setting file created when first added
    assert not os.path.isfile(setting_file)

    # Access it over "HTTP" with a TestClient
    # This doesn't actually serve over the network but will use
    # all the same codepaths.
    with TestClient(server.app) as client:
        if method == "http":
            # Attempt to set read-only setting
            r = client.put(f"/thing/{endpoint}", json=value)
            assert r.status_code == 405

        if method == "direct_thing_client":
            # Attempt to set read-only setting via a DirectThingClient
            r = client.post(f"/client_thing/set_{endpoint}", json={"val": value})
            assert r.status_code == 201
            invocation = poll_task(client, r.json())
            # The setting is not changed (that's tested later), but the action
            # does complete. It should fail with an error, but this is expected
            # behaviour - see #165.
            assert invocation["status"] == "error"

        # Check the setting hasn't changed over HTTP
        r = client.get(f"/thing/{endpoint}")
        assert r.json() == _settings_dict()[endpoint]
        assert r.status_code == 200

        if method == "direct":
            # Actually set read-only setting via raw_thing_dependency
            r = client.post(
                f"/client_thing/directly_set_{endpoint}", json={"val": value}
            )
            invocation = poll_task(client, r.json())
            assert invocation["status"] == "completed"

    if method == "direct":
        # Setting directly should succeed, so the file should exist.
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(**{endpoint: value})
    else:
        # Other methods fail, so there should be no file here.
        assert not os.path.isfile(setting_file)  # No file created


def test_settings_dict_save(server):
    """Check settings are saved if the dict is updated in full"""
    setting_file = _get_setting_file(server, "/thing")
    thing = server.add_thing("thing", ThingWithSettings)
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app):
        thing.dictsetting = {"c": 3}
        assert os.path.isfile(setting_file)
        with open(setting_file, "r", encoding="utf-8") as file_obj:
            # Check settings on file match expected dictionary
            assert json.load(file_obj) == _settings_dict(dictsetting={"c": 3})


def test_settings_dict_internal_update(server):
    """Confirm settings are not saved if the internal value of a dictionary is updated

    This behaviour is not ideal, but it is documented. If the behaviour is updated
    then the documentation should be updated and this test removed
    """
    setting_file = _get_setting_file(server, "/thing")
    thing = server.add_thing("thing", ThingWithSettings)
    # No setting file created when first added
    assert not os.path.isfile(setting_file)
    with TestClient(server.app):
        thing.dictsetting["a"] = 4
        # As only an internal member of the dictornary was set, the saving was not
        # triggered.
        assert not os.path.isfile(setting_file)


def test_settings_load(server):
    """Check settings can be loaded from disk when added to server"""
    setting_file = _get_setting_file(server, "/thing")
    setting_json = json.dumps(_settings_dict(floatsetting=3.0, stringsetting="bar"))
    # Create setting file
    os.makedirs(os.path.dirname(setting_file))
    with open(setting_file, "w", encoding="utf-8") as file_obj:
        file_obj.write(setting_json)
    # Add thing to server and check new settings are loaded
    thing = server.add_thing("thing", ThingWithSettings)
    assert not thing.boolsetting
    assert thing.stringsetting == "bar"
    assert thing.floatsetting == 3.0


def test_load_extra_settings(server, caplog):
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
        thing = server.add_thing("thing", ThingWithSettings)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].name == "labthings_fastapi.thing"

    # Check other settings are loaded as expected
    assert not thing.boolsetting
    assert thing.stringsetting == "bar"
    assert thing.floatsetting == 3.0


def test_try_loading_corrupt_settings(server, caplog):
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
        thing = server.add_thing("thing", ThingWithSettings)
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].name == "labthings_fastapi.thing"

    # Check default settings are loaded
    assert not thing.boolsetting
    assert thing.stringsetting == "foo"
    assert thing.floatsetting == 1.0
