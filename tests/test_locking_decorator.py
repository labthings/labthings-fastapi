import time
from typing import Callable, TypeVar, ParamSpec
import functools
from threading import RLock, Event, Thread

from fastapi.testclient import TestClient
import pytest

import labthings_fastapi as lt
from labthings_fastapi.testing import create_thing_without_server
from .temp_client import poll_task


Value = TypeVar("Value")
Params = ParamSpec("Params")


def requires_lock(func: Callable[Params, Value]) -> Callable[Params, Value]:
    """Decorate an action to require a lock."""

    @functools.wraps(func)
    def locked_func(*args, **kwargs):
        lock: RLock = args[0]._lock
        if not lock.acquire(blocking=False):
            raise TimeoutError("Could not lock.")
        try:
            return func(*args, **kwargs)
        finally:
            lock.release()

    return locked_func


class LockedExample(lt.Thing):
    """A Thing where only one action may happen at a time."""

    flag: bool = lt.property(default=False)

    def __init__(self, **kwargs):
        """Initialise the lock."""
        super().__init__(**kwargs)
        self._lock = RLock()  # This lock is used by @requires_lock
        self._event = Event()  # This is used to keep tests quick
        # by stopping waits as soon as they are no longer needed

    @lt.action
    @requires_lock
    def wait_wrapper(self, time: float = 1) -> None:
        """Wait a specified time, calling wait_with_flag.

        This lets us check the RLock correctly allows one locked
        function to call another.
        """
        self.wait_with_flag(time)

    @lt.action
    @requires_lock
    def echo(self, message: str) -> str:
        """Echo a message back to the sender."""
        return message

    @lt.action
    @requires_lock
    def wait_with_flag(self, time: float = 1) -> None:
        """Wait a specified time with the flag True."""
        assert self.flag is False
        self.flag = True
        self._event.wait(time)
        self.flag = False


@pytest.fixture
def thing(mocker) -> LockedExample:
    """Instantiate the LockedExample thing."""
    thing = create_thing_without_server(LockedExample)
    return thing


def test_echo(thing: LockedExample) -> None:
    """Check the example function works.

    Having this in a test function means if it raises an
    exception, we can be sure it's because of the lock, and
    not just a typo in the test.
    """
    assert thing.echo("test") == "test"


def wait_for_flag(thing: LockedExample) -> None:
    """Wait until the flag is set, so we know the lock is acquired."""
    while not thing.flag:
        time.sleep(0.001)


def test_locking(thing: LockedExample) -> None:
    """Check the lock prevents concurrent access."""
    thread = Thread(target=thing.wait_wrapper)
    thread.start()
    wait_for_flag(thing)
    with pytest.raises(TimeoutError):
        # This should fail because the lock is acquired
        test_echo(thing)
    thing._event.set()  # tell the thread to stop
    thread.join()
    # Check the lock is now released - other actions should work
    test_echo(thing)


def echo_via_client(client):
    """Use a POST request to run the echo action."""
    r = client.post("/thing/echo", json={"message": "test"})
    r.raise_for_status()
    return poll_task(client, r.json())


def test_locking_in_server():
    """Check the lock works within LabThings."""
    server = lt.ThingServer({"thing": LockedExample})
    thing = server.things["thing"]
    with TestClient(server.app) as client:
        # Start a long task
        r1 = client.post("/thing/wait_wrapper", json={})
        # Wait for it to start
        while client.get("/thing/flag").json() is not True:
            time.sleep(0.01)
        # Try another action and check it fails
        inv2 = echo_via_client(client)
        assert inv2["status"] == "error"
        # Instruct the first task to stop
        thing._event.set()  # stop the first action
        inv1 = poll_task(client, r1.json())  # wait for it to complete
        assert inv1["status"] == "completed"  # check there's no error
        # This action should succeed now
        inv3 = echo_via_client(client)
        assert inv3["status"] == "completed"
        assert inv3["output"] == "test"
