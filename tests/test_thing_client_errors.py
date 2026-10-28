"""Test how errors in actions and properties are reported to the client."""

import threading
from collections.abc import Iterator

import pytest

import labthings_fastapi as lt
from labthings_fastapi.client import poll_invocation
from labthings_fastapi.exceptions import (
    GlobalLockBusyError,
    InvocationCancelledError,
    ServerActionError,
)


class CustomError(Exception):
    """An error that's neither part of the standard library nor LabThings."""


class ErrorThing(lt.Thing):
    @lt.action
    def raise_custom_error(self) -> None:
        """Raise a custom Exception."""
        raise CustomError("custom error message.")

    @lt.action
    def raise_runtime_error(self) -> None:
        """Raise a RuntimeError."""
        raise RuntimeError("runtime error message.")

    @lt.action
    def raise_global_lock_error(self) -> None:
        """Raise a GlobaLockBusyError after the action's started."""
        raise GlobalLockBusyError("this action has already started.")

    @lt.action
    def raise_invocation_cancelled_error(self) -> None:
        """Raise an InvocationCancelledError, pretend to be cancelled."""
        raise InvocationCancelledError("pretending to be cancelled.")


@pytest.fixture
def server() -> lt.ThingServer:
    """Make a server with the Thing attached."""
    return lt.ThingServer.from_things({"thing": ErrorThing}, enable_global_lock=True)


@pytest.fixture
def thing(server: lt.ThingServer) -> ErrorThing:
    """extract the thing from the server."""
    thing = server.things["thing"]
    assert isinstance(thing, ErrorThing)
    return thing


@pytest.fixture
def client(server: lt.ThingServer) -> Iterator[lt.ThingClient]:
    """Connect a ThingClient to the thing."""
    with server.test_client() as tc:
        yield lt.ThingClient.from_url("/thing/", client=tc)


@pytest.fixture
def hold_global_lock(thing):
    """Hold the global lock in a background thread.

    This allows us to test for actions that fail to start.
    """
    _event = threading.Event()
    _global_lock = thing._thing_server_interface.global_lock
    assert _global_lock
    _global_lock.default_timeout = 0.001  # reduce time spent waiting

    def _hold_lock():
        try:
            thing._thing_server_interface.global_lock.acquire()
            _event.wait()
        finally:
            thing._thing_server_interface.global_lock.release()

    thread = threading.Thread(target=_hold_lock)
    thread.start()
    try:
        yield
    finally:
        _event.set()
        thread.join()


_original_poll_invocation = poll_invocation


def poll_and_delete_error(client, invocation):
    """Wrap poll_invocation to hide the `error` key."""
    output = _original_poll_invocation(client, invocation)
    del output["error"]
    return output


@pytest.fixture
def delete_error_info(mocker):
    mocker.patch("labthings_fastapi.client.poll_invocation", poll_and_delete_error)


def test_custom_error(client):
    """Test that the custom error is properly reported."""
    with pytest.raises(ServerActionError, match="[CustomError]: custom error message."):
        client.raise_custom_error()


def test_custom_error_old(client, delete_error_info):
    """Test that the custom error is properly reported if the `error` key is missing."""
    with pytest.raises(ServerActionError, match="[CustomError]: custom error message."):
        client.raise_custom_error()


def test_runtime_error(client):
    """Test that the custom error is properly reported."""
    with pytest.raises(
        ServerActionError, match="[RuntimeError]: runtime error message."
    ):
        client.raise_runtime_error()


def test_runtime_error_old(client, delete_error_info):
    """Test that the custom error is properly reported if the `error` key is missing."""
    with pytest.raises(
        ServerActionError, match="[RuntimeError]: runtime error message."
    ):
        client.raise_runtime_error()


def test_global_lock_error(client):
    """Test a global lock error encountered during the action."""
    with pytest.raises(GlobalLockBusyError, match="this action has already started."):
        client.raise_global_lock_error()


def test_global_lock_error_old(client, delete_error_info):
    """Test a global lock error encountered during the action (no error key)."""
    with pytest.raises(
        ServerActionError,
        match="[GlobalLockBusyError]: this action has already started.",
    ):
        client.raise_global_lock_error()


def test_invocation_cancelled_error(client):
    """Test a simulated cancellation."""
    with pytest.raises(InvocationCancelledError, match="pretending to be cancelled."):
        client.raise_invocation_cancelled_error()


def test_invocation_cancelled_error_old(client, delete_error_info):
    """Test a simulated cancellation without the `error` key in the response."""
    with pytest.raises(ServerActionError, match="was cancelled."):
        client.raise_invocation_cancelled_error()


def test_failure_to_start(client, hold_global_lock):
    """Test the error that happens if the global lock is busy."""
    with pytest.raises(
        GlobalLockBusyError, match="The global lock could not be acquired"
    ):
        client.raise_runtime_error()  # The action is unimportant as it never starts


def test_failure_to_start_old(client, hold_global_lock, delete_error_info):
    """Test the error that happens if the global lock is busy, without `error`."""
    with pytest.raises(ServerActionError, match="didn't run raise_runtime_error"):
        client.raise_runtime_error()  # The action is unimportant as it never starts
