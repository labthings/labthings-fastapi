"""Test the ThingServerInterface class and associated features."""

import gc
import os
import tempfile
from typing import Mapping
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import ServerNotRunningError, ThingNotConnectedError
from labthings_fastapi.thing_server_interface import (
    ThingServerInterface,
    ThingServerMissingError,
)
from labthings_fastapi.testing import (
    MockThingServerInterface,
    create_thing_without_server,
)

NAME = "testname"
EXAMPLE_THING_STATE = {"foo": "bar"}


class ExampleThing(lt.Thing):
    @lt.property
    def thing_state(self):
        return EXAMPLE_THING_STATE


class DifferentExampleThing(lt.Thing):
    pass


class AnotherExampleThing(lt.Thing):
    pass


class UnusedExampleThing(lt.Thing):
    pass


class GroupedThing(lt.Thing):
    pass


class DifferentGroupedThing(lt.Thing):
    pass


DIF_EXAMPLE_NAME = "diffy"
DIF_GROUPED_NAMES = ["snap", "crackle", "pop"]


class ExampleWithSlots(lt.Thing):
    example: ExampleThing = lt.thing_slot()
    dif_example: DifferentExampleThing = lt.thing_slot(DIF_EXAMPLE_NAME)
    optionally_another_example: AnotherExampleThing | None = lt.thing_slot()
    unused_option: UnusedExampleThing | None = lt.thing_slot(None)
    grouped_things: Mapping[str, GroupedThing] = lt.thing_slot()
    dif_grouped_things: Mapping[str, DifferentGroupedThing] = lt.thing_slot(
        DIF_GROUPED_NAMES
    )


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
    return ThingServerInterface(server, NAME)


@pytest.fixture
def mockinterface():
    """Return a MockThingServerInterface."""
    return MockThingServerInterface(NAME)


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
    interface = ThingServerInterface(server, NAME)
    assert interface._get_server() is server
    del server
    gc.collect()
    with pytest.raises(ThingServerMissingError):
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


def test_action_manager(server, interface):
    """Check the action manager is retrieved properly."""
    assert interface._action_manager is server.action_manager


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


def test_mock_action_manager(mockinterface):
    """Check that accessing the action manager raises an error."""
    with pytest.raises(NotImplementedError):
        _ = mockinterface._action_manager


def test_create_thing_without_server():
    """Check the test harness for creating things without a server."""
    example = create_thing_without_server(ExampleThing)
    assert isinstance(example, ExampleThing)
    assert example.path == "/examplething/"
    assert isinstance(example._thing_server_interface, MockThingServerInterface)

    # Check we can specify the settings location
    with tempfile.TemporaryDirectory() as folder:
        ex2 = create_thing_without_server(ExampleThing, settings_folder=folder)
        assert ex2._thing_server_interface.settings_file_path == os.path.join(
            folder, "settings.json"
        )

    # We can't supply the interface as a kwarg
    with pytest.raises(ValueError, match="may not supply"):
        create_thing_without_server(ExampleThing, thing_server_interface=None)


def test_not_mocking_slots():
    """Check slots are not mocked by default."""
    slotty = create_thing_without_server(ExampleWithSlots)

    with pytest.raises(ThingNotConnectedError):
        _ = slotty.example
    with pytest.raises(ThingNotConnectedError):
        _ = slotty.dif_example
    with pytest.raises(ThingNotConnectedError):
        _ = slotty.optionally_another_example
    with pytest.raises(ThingNotConnectedError):
        _ = slotty.unused_option
    with pytest.raises(ThingNotConnectedError):
        _ = slotty.grouped_things
    with pytest.raises(ThingNotConnectedError):
        _ = slotty.dif_grouped_things


def test_mocking_slots():
    """Check the type of things and thing connections is correctly determined."""
    slotty = create_thing_without_server(ExampleWithSlots, mock_all_slots=True)

    # example is a mock pretending to be an ExampleThing
    assert isinstance(slotty.example, ExampleThing)
    assert isinstance(slotty.example, Mock)

    # dif_example is a mock pretending to be a DifferentExampleThing, its name is set.
    assert isinstance(slotty.dif_example, DifferentExampleThing)
    assert isinstance(slotty.dif_example, Mock)
    assert slotty.dif_example.name == DIF_EXAMPLE_NAME

    # optionally_another_example, was optional but should be a mock pretending to be
    # a AnotherExampleThing
    assert isinstance(slotty.optionally_another_example, AnotherExampleThing)
    assert isinstance(slotty.optionally_another_example, Mock)

    # unused_option was an optional slot, but defaults to None. So should be None
    assert slotty.unused_option is None

    # The grouped_things should be a mapping
    assert isinstance(slotty.grouped_things, Mapping)
    for thing in slotty.grouped_things.values():
        # All of the things should be mocks pretenting to be a GroupedThing
        assert isinstance(thing, GroupedThing)
    # No default so only one was created
    assert len(slotty.grouped_things) == 1

    # The dif_grouped_things should be a mapping
    assert isinstance(slotty.dif_grouped_things, Mapping)
    # The keys should be set from DIF_GROUPED_NAMES
    assert set(DIF_GROUPED_NAMES) == set(slotty.dif_grouped_things.keys())
    # These should also be the thing names
    grouped_thing_names = {i.name for i in slotty.dif_grouped_things.values()}
    assert set(DIF_GROUPED_NAMES) == grouped_thing_names
