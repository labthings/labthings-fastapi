"""Test code for the global lock."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread

import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import (
    ClientPropertyError,
    GlobalLockBusyError,
    ServerActionError,
)
from labthings_fastapi.global_lock import GlobalLock
from labthings_fastapi.testing import create_thing_without_server

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
    """A class to check if actions may run concurrently.

    See `check_for_changes_unlocked` for some important concurrency notes.
    """

    def __init__(self, thing_server_interface: lt.ThingServerInterface):
        super().__init__(thing_server_interface)
        self._tick_event = Event()
        self._tock_event = Event()
        self._fprop1 = 0
        self._fprop2 = 0

    @lt.action(use_global_lock=False)
    def tick(self):
        """Set the tick event and block until it's acknowledged.

        This avoids race conditions in the test code, by ensuring
        the checks performed by `check_for_changes_unlocked` happen at
        well-defined points in the foreground thread. See that method
        for more details.
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
        r"""Check if any properties have changed.

        This function does not acquire the global lock.

        In order to minimise dead time and remove the need for lots of `time.sleep`
        calls, this method is synchronised by `_tick_event` and `_tock_event` and
        terminated with `keep_checking_for_changes`\ .

        Code using this method should run it in a background thread or action
        (most likely using the `monitor_for_changes` context manager) and then
        set `changes_detected` to `False` then
        call the `tick()` action whenever a check is required. Once the `tick()`
        action has completed, `changes_detected` will be set to the right value
        and the property values will be reset.

        The routine above is done automatically by `assert_changes` or `assert fails`
        when run as context managers.

        At the end of the test (or when `monitor_for_changes` exits), you should
        set `keep_checking_for_changes` to `False` and call `tick()` one last time
        before `join()`\ ing the thread. Doing this using the context manager
        should ensure your test code does not hang when it fails.
        """
        names = ["prop1", "prop2", "fprop1", "fprop2"]
        initial_values = {n: getattr(self, n) for n in names}
        self.logger.info("Checking for changes")
        while self.keep_checking_for_changes:
            self._tick_event.wait(timeout=0.1)
            self._tick_event.clear()
            for n in names:
                # Check for changes and reset to initial state
                if getattr(self, n) != initial_values[n]:
                    self.changes_detected = True
                    setattr(self, n, initial_values[n])
            self._tock_event.set()
        self.logger.info("Finished checking for changes.")

    check_for_changes_unlocked.use_global_lock = False

    @lt.action
    def check_for_changes_locked(self):
        """This runs `check_for_changes_unlocked` but acquires the lock."""
        self.logger.info("Checking for changes and holding lock.")
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
    """Assert the code in a with block does or does not change properties.

    See `ConcurrencyChecker.check_for_changes_unlocked` for notes on synchronisation.
    """
    thing.changes_detected = False
    yield
    thing.tick()
    assert thing.changes_detected is True


@contextmanager
def assert_fails(thing: ConcurrencyChecker) -> Iterator[None]:
    """Assert that the code in a with block fails with an error.

    Currently, this will look for several exceptions, so that it works on both client
    and server-side.

    See `ConcurrencyChecker.check_for_changes_unlocked` for notes on synchronisation.
    """
    thing.changes_detected = False
    with pytest.raises((GlobalLockBusyError, ServerActionError, ClientPropertyError)):
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
        thing.tick()
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


def test_global_lock_release_unacquired():
    """Make sure the same error is raised as for RLock for spurious release."""
    lock = GlobalLock()
    with pytest.raises(RuntimeError):
        lock.release()  # The lock was never acquired.


def test_global_lock_identity():
    """Ensure the property returns the exact same lock instance every time."""
    server = lt.ThingServer.from_things({}, enable_global_lock=True)
    interface = lt.ThingServerInterface(server, "thing_name", "ThingClass")

    lock_1 = interface.global_lock
    lock_2 = interface.global_lock

    assert lock_1 is lock_2, "The interface is generating multiple distinct locks!"


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

    # acquire() should respect the timeout argument
    with assert_takes_time(None, 0.04):
        assert lock.acquire(timeout=0) is False
    with assert_takes_time(0.06, 0.12):
        assert lock.acquire(timeout=0.1) is False

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
    # Each action is called twice to check for reuse of context managers.
    with assert_changes(thing):
        thing.increment_fprop2()
    with assert_changes(thing):
        thing.increment_prop1()
    with assert_changes(thing):
        thing.increment_fprop2_unlocked()
    with assert_changes(thing):
        thing.increment_fprop2()
    with assert_changes(thing):
        thing.increment_prop1()
    with assert_changes(thing):
        thing.increment_fprop2_unlocked()


def assertions_with_locking(thing: ConcurrencyChecker):
    """Test that only the unlocked actions and properties produce a change.

    Note that this requires `check_for_changes_locked` to be running in a background
    thread. See `assertions_without_locking` for a version that should work with locking
    disabled.

    This should run if either a `ConcurrencyChecker` or a `ThingClient` connected to
    one is supplied.
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
    with assert_fails(thing):
        thing.increment_fprop2()

    # Actions may run if they're excluded from the lock.
    # Note this is done twice to check for reuse of context managers.
    # (There is no expected failure, because we don't reuse the
    # context manager. However, running the test below twice did
    # fail, when a generator context manager was being inappropriately
    # reused.)
    with assert_changes(thing):
        thing.increment_fprop2_unlocked()
    with assert_changes(thing):
        thing.increment_fprop2_unlocked()

    # Actions that use locked resources (like prop1) should also fail
    with assert_fails(thing):
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

    This test uses TestClient, with locking enabled.
    """
    server = lt.ThingServer.from_things(
        {"checker": ConcurrencyChecker}, enable_global_lock=True
    )
    with server.test_client() as client:
        thing = lt.ThingClient.from_url("/checker/", client=client)
        with monitor_for_changes(thing, hold_lock=True):
            assertions_with_locking(thing)
        with monitor_for_changes(thing, hold_lock=False):
            assertions_without_locking(thing)


def test_actions_and_properties_testclient_lock_disabled():
    """Ensure the global lock stops multiple things happening at once.

    This test uses a TestClient, with locking disabled.
    """
    server = lt.ThingServer.from_things(
        {"checker": ConcurrencyChecker}, enable_global_lock=False
    )
    with server.test_client() as client:
        thing = lt.ThingClient.from_url("/checker/", client=client)
        with monitor_for_changes(thing, hold_lock=True):
            assertions_without_locking(thing)
        with monitor_for_changes(thing, hold_lock=False):
            assertions_without_locking(thing)


def test_reuse_of_action_callables():
    """Test that it's OK to get a bound action and call it multiple times."""
    thing = create_thing_without_server(ConcurrencyChecker, enable_global_lock=True)
    with monitor_for_changes(thing, hold_lock=False):
        func = thing.increment_fprop2
        with assert_changes(thing):
            func()
        with assert_changes(thing):
            func()


def test_global_lock_log(caplog):
    """Test that we get sensible errors when the lock is busy."""
    server = lt.ThingServer.from_things(
        {"checker": ConcurrencyChecker}, enable_global_lock=True
    )
    with server.test_client() as client:
        checker = lt.ThingClient.from_url("/checker/", client=client)

        with monitor_for_changes(checker, hold_lock=True):
            # First, try a function that uses the global lock.
            # This should fail with a message about the global
            # lock, but no traceback.
            caplog.clear()
            with pytest.raises(
                GlobalLockBusyError,
                match="The global lock could not be acquired",
            ):
                checker.increment_fprop2()
            matches = [r for r in caplog.records if "Global lock was busy" in r.message]
            assert len(matches) == 1
            assert matches[0].levelno == logging.WARNING
            assert "Traceback" not in caplog.text

            # Next, try the same thing with an action that does
            # not hold the global lock, but calls a property that
            # does. This should print a stack trace, as the
            # exception is not handled.
            caplog.clear()
            with pytest.raises(GlobalLockBusyError):
                checker.increment_prop1()
            assert "Traceback" in caplog.text
