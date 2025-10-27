"""Test the ThingServerInterface class and associated features."""

import gc
import os
import tempfile

from fastapi.testclient import TestClient
import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import ServerNotRunningError
from labthings_fastapi import thing_server_interface as tsi


NAME = "testname"
EXAMPLE_THING_STATE = {"foo": "bar"}


class ExampleThing(lt.Thing):
    @lt.property
    def thing_state(self):
        return EXAMPLE_THING_STATE


@pytest.fixture
def server():
    """Return a LabThings server"""
    with tempfile.TemporaryDirectory() as dir:
        server = lt.ThingServer(
            things={"example": ExampleThing},
            settings_folder=dir,
        )
        yield server


@pytest.fixture
def interface(server):
    """Return a ThingServerInterface, connected to a server."""
    return tsi.ThingServerInterface(server, NAME)


@pytest.fixture
def mockinterface():
    """Return a MockThingServerInterface."""
    return tsi.MockThingServerInterface(NAME)


def test_get_server(server, interface):
    """Check the server is retrieved correctly.

    This also tests for the right error if it's missing.
    """
    assert interface._get_server() is server


def test_get_server_error():
    """Ensure a helpful error is raised if the server is deleted.

    This is an error condition that I would find surprising if it
    ever occurred, but it's worth checking.
    """
    server = lt.ThingServer(things={})
    interface = tsi.ThingServerInterface(server, NAME)
    assert interface._get_server() is server
    del server
    gc.collect()
    with pytest.raises(tsi.ThingServerMissingError):
        interface._get_server()


def test_start_async_task_soon(server, interface):
    """Check async tasks may be run in the event loop."""
    mutable = [False]

    async def set_mutable(val):
        mutable[0] = val

    with pytest.raises(ServerNotRunningError):
        # You can't run async code unless the server
        # is running: this should raise a helpful
        # error.
        interface.start_async_task_soon(set_mutable, True)

    with TestClient(server.app) as _:
        # TestClient starts an event loop in the background
        # so this should work
        interface.start_async_task_soon(set_mutable, True)

    # Check the async code really did run.
    assert mutable[0] is True


def test_settings_folder(server, interface):
    """Check the interface returns the right settings folder."""
    assert interface.settings_folder == os.path.join(server.settings_folder, NAME)


def test_settings_file_path(server, interface):
    """Check the settings file path is as expected."""
    assert interface.settings_file_path == os.path.join(
        server.settings_folder, NAME, "settings.json"
    )


def test_name(server, interface):
    """Check the thing's name is passed on correctly."""
    assert interface.name is NAME
    assert server.things["example"]._thing_server_interface.name == "example"


def test_path(interface, server):
    """Check the thing's path is generated predictably."""
    with pytest.raises(KeyError):
        # `interface` is for a thing called NAME, which isn't
        # added to the server, so when we try to get its path
        # it should raise an error.
        _ = interface.path
    # If we put something in the dictionary of things, it should work.
    server._things[NAME] = None
    assert interface.path == f"/{NAME}/"
    # We can also check the example thing, which is actually added to the server.
    # This doesn't need any mocking.
    assert server.things["example"].path == "/example/"


def test_get_thing_states(interface):
    """Check thing metadata is retrieved properly."""
    states = interface.get_thing_states()
    assert states == {"example": EXAMPLE_THING_STATE}


def test_mock_start_async_task_soon(mockinterface):
    """Check nothing happens when we run an async task."""
    mutable = [False]

    async def set_mutable(val):
        mutable[0] = val

    mockinterface.start_async_task_soon(set_mutable, True)

    # Check the async code didn't run
    assert mutable[0] is False


def test_mock_settings_folder(mockinterface):
    """Check a temporary settings folder is provided."""
    # The temp folder should be created when accessed,
    # so is None initially.
    assert mockinterface._settings_tempdir is None
    f = mockinterface.settings_folder
    assert f == mockinterface._settings_tempdir.name
    assert mockinterface.settings_file_path == os.path.join(f, "settings.json")


def test_mock_path(mockinterface):
    """Check the path is generated predictably."""
    assert mockinterface.path == f"/{NAME}/"


def test_mock_get_thing_states(mockinterface):
    """Check an empty dictionary is returned."""
    assert mockinterface.get_thing_states() == {}


def test_create_thing_without_server():
    """Check the test harness for creating things without a server."""
    example = tsi.create_thing_without_server(ExampleThing)
    assert isinstance(example, ExampleThing)
    assert example.path == "/examplething/"
    assert isinstance(example._thing_server_interface, tsi.MockThingServerInterface)
