"""Test code for the global lock."""

from collections.abc import Iterator
from threading import Thread, Event
from fastapi.testclient import TestClient
import pytest
from contextlib import contextmanager

from labthings_fastapi.exceptions import GlobalLockBusyError, ServerActionError
from labthings_fastapi.testing import create_thing_without_server
from labthings_fastapi.global_lock import GlobalLock
import labthings_fastapi as lt

from .utilities import assert_takes_time


class LockChecker(Thread):
    def __init__(self, lock: GlobalLock):
        super().__init__()
        self._lock = lock

    def run(self):
        self.acquired = self._lock.acquire(blocking=False)
        if self.acquired:
            self._lock.release()


def lock_is_available(lock: GlobalLock) -> bool:
    """Check whether a lock is locked.

    This is needed for Python < 3.14 as there's no `locked` property.
    """
    checker = LockChecker(lock)
    checker.start()
    checker.join()
    return checker.acquired


class ConcurrencyChecker(lt.Thing):
    """A class to check if actions may run concurrently."""

    def __init__(self, thing_server_interface: lt.ThingServerInterface):
        super().__init__(thing_server_interface)
        self._tick_event = Event()
        self._tock_event = Event()
        self._fprop1 = 0
        self._fprop2 = 0

    @lt.action(use_global_lock=False)
    def tick(self):
        """Set the tick event and block until it's acknowledged.

        This avoids race conditions in the test code.
        """
        self._tick_event.set()
        self._tock_event.wait(0.1)
        self._tock_event.clear()

    changes_detected: bool = lt.property(default=False, use_global_lock=False)

    prop1: int = lt.property(default=0)
    """A data property, subject to the global lock by default."""

    prop2: int = lt.property(default=0, use_global_lock=False)
    """A data property that may be changed without the lock."""

    @lt.property
    def fprop1(self) -> int:
        """A functional property that is locked (by default)."""
        return self._fprop1

    @fprop1.setter
    def _set_fprop1(self, val: int) -> None:
        self._fprop1 = val

    @lt.property
    def fprop2(self) -> int:
        """A functional property that is not locked."""
        return self._fprop2

    fprop2.use_global_lock = False

    @fprop2.setter
    def _set_fprop2(self, val: int) -> None:
        self._fprop2 = val

    keep_checking_for_changes: bool = lt.property(default=False, use_global_lock=False)
    """Set this to False to stop checking for changes."""

    @lt.action
    def check_for_changes_unlocked(self) -> None:
        """Check if any properties have changed.

        This function does not acquire the global lock.

        :param ticks: the number of times to wait for the tick event.
        :return: whether any changes were detected.
        """
        names = ["prop1", "prop2", "fprop1", "fprop2"]
        initial_values = {n: getattr(self, n) for n in names}
        while self.keep_checking_for_changes:
            self._tick_event.wait(timeout=0.1)
            self._tick_event.clear()
            for n in names:
                # Check for changes and reset to initial state
                if getattr(self, n) != initial_values[n]:
                    self.changes_detected = True
                    setattr(self, n, initial_values[n])
            self._tock_event.set()

    check_for_changes_unlocked.use_global_lock = False

    @lt.action
    def check_for_changes_locked(self):
        """This runs `check_for_changes_unlocked` but acquires the lock."""
        return self.check_for_changes_unlocked()

    @lt.action
    def increment_fprop2(self):
        """Increment fprop2, subject to the global lock."""
        self._fprop2 += 1
        self.logger.info(f"increment_fprop2 set _fprop2 to {self._fprop2}")

    @lt.action
    def increment_fprop2_unlocked(self):
        """Increment fprop2, not subject to the global lock."""
        self._fprop2 += 1
        self.logger.info(f"increment_fprop2_unlocked set _fprop2 to {self._fprop2}")

    increment_fprop2_unlocked.use_global_lock = False

    @lt.action
    def increment_prop1(self):
        """This function is excluded from the lock - but prop1 is locked.

        This function should therefore fail if the lock is in use.
        """
        self.prop1 += 1
        self.logger.info(f"increment_prop1 set prop1 to {self.prop1}")

    increment_prop1.use_global_lock = False


@contextmanager
def assert_changes(thing: ConcurrencyChecker):
    """Assert the code in a with block does or does not change properties."""
    thing.changes_detected = False
    yield
    thing.tick()
    assert thing.changes_detected is True


@contextmanager
def assert_fails(
    thing: ConcurrencyChecker, error: type[Exception] = GlobalLockBusyError
) -> Iterator[None]:
    """Assert that the code in a with block doesn't change properties and errors."""
    thing.changes_detected = False
    with pytest.raises(error):
        yield
    thing.tick()
    assert thing.changes_detected is False


@contextmanager
def monitor_for_changes(thing: ConcurrencyChecker, hold_lock: bool) -> Iterator[None]:
    """Monitor for changes in a background thread"""
    # Start the background action that checks for changes.
    monitor_thread = Thread(
        target=(
            thing.check_for_changes_locked
            if hold_lock
            else thing.check_for_changes_unlocked
        ),
    )
    thing.keep_checking_for_changes = True
    monitor_thread.start()
    try:
        yield

        assert monitor_thread.is_alive()
    except Exception:
        # If an exception occurs, send ticks so the background process terminates
        print(
            "monitor_for_changes caught an exception. "
            f"Background thread is {'alive' if monitor_thread.is_alive() else 'dead'}."
        )
        raise
    finally:
        thing.keep_checking_for_changes = False
        thing.tick()
        monitor_thread.join()


def test_global_lock_unthreaded():
    """Test that the global lock acquires and releases the underlying `RLock`"""
    lock = GlobalLock()
    lock.default_timeout = 0.001

    # The lock starts out available
    assert lock_is_available(lock)

    # Once acquired, it's not available to other threads
    lock.acquire()
    assert not lock_is_available(lock)

    # It should be acquireable several times in this thread
    lock.acquire()
    assert not lock_is_available(lock)
    lock.release()

    # It needs to be released once per acquire call
    assert not lock_is_available(lock)
    lock.release()
    assert lock_is_available(lock)

    # The same thing should work with context manager use
    with lock:
        assert not lock_is_available(lock)
        with lock:
            assert not lock_is_available(lock)
        assert not lock_is_available(lock)
    assert lock_is_available(lock)

    # Or mixed use
    with lock:
        assert not lock_is_available(lock)
        lock.acquire()
        assert not lock_is_available(lock)
        with lock:
            lock.acquire()
            assert not lock_is_available(lock)
            lock.release()
            assert not lock_is_available(lock)
        lock.release()
        assert not lock_is_available(lock)
    assert lock_is_available(lock)


def test_global_lock_timeout():
    """Check the global lock times out correctly."""
    lock = GlobalLock()
    lock.default_timeout = 0.05
    finished = Event()

    def hold_lock_in_background():
        with lock:
            finished.wait(5)

    # Hold the lock in another thread
    t = Thread(target=hold_lock_in_background)
    t.start()

    # acquire() with no arguments should use the default timeout
    with assert_takes_time(0.045, 0.1):
        assert lock.acquire() is False
    with assert_takes_time(0.045, 0.1):
        assert lock.acquire(blocking=True) is False

    # check non-blocking acquire() works
    with assert_takes_time(None, 0.001):
        assert lock.acquire(blocking=False) is False

    # context manager use should also use the default timeout
    with assert_takes_time(0.045, 0.1):
        with pytest.raises(GlobalLockBusyError):
            with lock:
                pass

    # check the lock is still being held
    assert t.is_alive
    finished.set()
    t.join()


def assertions_without_locking(thing: ConcurrencyChecker):
    """Test that all the actions and properties produce a change.

    Note that this requires `check_for_changes` or `check_for_changes_unlocked`
    to be running in a background thread.
    """
    # When we are using the non-blocking checker, all the properties should work.
    with assert_changes(thing):
        thing.prop1 += 1
    with assert_changes(thing):
        thing.prop2 += 1
    with assert_changes(thing):
        thing.fprop1 += 1
    with assert_changes(thing):
        thing.fprop2 += 1

    # Increment actions should work too.
    with assert_changes(thing):
        thing.increment_fprop2()
    with assert_changes(thing):
        thing.increment_prop1()
    with assert_changes(thing):
        thing.increment_fprop2_unlocked()


def assertions_with_locking(
    thing: ConcurrencyChecker, action_error: type[Exception] = GlobalLockBusyError
):
    """Test that only the unlocked actions and properties produce a change.

    Note that this requires `check_for_changes_locked` to be running in a background
    thread. See `assertions_without_locking` for a version that should work with locking
    disabled.
    """
    # Properties may always be read
    assert thing.prop1 == 0
    assert thing.prop2 == 0
    assert thing.fprop1 == 0
    assert thing.fprop2 == 0

    # When we are holding the lock, by default properties can't be written.
    with assert_fails(thing):
        thing.prop1 += 1
    with assert_fails(thing):
        thing.fprop1 += 1

    # The properties excluded from the lock may still be written
    with assert_changes(thing):
        thing.prop2 += 1
    with assert_changes(thing):
        thing.fprop2 += 1

    # By default actions won't run
    with assert_fails(thing, error=action_error):
        thing.increment_fprop2()

    # Actions may run if they're excluded from the lock.
    with assert_changes(thing):
        thing.increment_fprop2_unlocked()

    # Actions that use locked resources (like prop1) should also fail
    with assert_fails(thing, error=action_error):
        thing.increment_prop1()


def test_actions_and_properties_direct_lock_enabled():
    """Ensure the global lock stops multiple things happening at once.

    This test uses a Thing instance directly, with locking enabled.
    """
    thing = create_thing_without_server(ConcurrencyChecker, enable_global_lock=True)
    with monitor_for_changes(thing, hold_lock=True):
        assertions_with_locking(thing)
    with monitor_for_changes(thing, hold_lock=False):
        assertions_without_locking(thing)


def test_actions_and_properties_direct_lock_disabled():
    """Ensure the global lock stops multiple things happening at once.

    This test uses a Thing instance directly, with locking disabled.
    """
    thing = create_thing_without_server(ConcurrencyChecker, enable_global_lock=False)
    with monitor_for_changes(thing, hold_lock=True):
        assertions_without_locking(thing)
    with monitor_for_changes(thing, hold_lock=False):
        assertions_without_locking(thing)


def test_actions_and_properties_testclient_lock_enabled():
    """Ensure the global lock stops multiple things happening at once.

    This test uses a Thing instance directly, with locking enabled.
    """
    server = lt.ThingServer({"checker": ConcurrencyChecker}, enable_global_lock=True)
    with TestClient(server.app) as client:
        thing = lt.ThingClient.from_url("/checker/", client=client)
        with monitor_for_changes(thing, hold_lock=True):
            assertions_with_locking(thing, action_error=ServerActionError)
        with monitor_for_changes(thing, hold_lock=False):
            assertions_without_locking(thing)


def test_actions_and_properties_testclient_lock_disabled():
    """Ensure the global lock stops multiple things happening at once.

    This test uses a Thing instance directly, with locking enabled.
    """
    server = lt.ThingServer({"checker": ConcurrencyChecker}, enable_global_lock=False)
    with TestClient(server.app) as client:
        thing = lt.ThingClient.from_url("/checker/", client=client)
        with monitor_for_changes(thing, hold_lock=True):
            assertions_without_locking(thing)
        with monitor_for_changes(thing, hold_lock=False):
            assertions_without_locking(thing)
