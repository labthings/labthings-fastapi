"""Test code for the global lock."""

from threading import Thread, Event
from labthings_fastapi.exceptions import GlobalLockBusyError
from labthings_fastapi.testing import create_thing_without_server
import pytest

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


class ConcurrencyChecker(lt.Thing):
    """A class to check if actions may run concurrently."""

    def __init__(self, thing_server_interface: lt.ThingServerInterface):
        super().__init__(thing_server_interface)
        self._tick_event = Event()
        self._tock_event = Event()
        self._fprop1 = 0
        self._fprop2 = 0

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

    @lt.action
    def check_for_changes_unlocked(self, ticks=2) -> None:
        """Check if any properties have changed.

        This function does not acquire the global lock.

        :param ticks: the number of times to wait for the tick event.
        :return: whether any changes were detected.
        """
        names = ["prop1", "prop2", "fprop1", "fprop2"]
        initial_values = {n: getattr(self, n) for n in names}
        for _i in range(ticks):
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
    def check_for_changes_locked(self, ticks=2):
        return self.check_for_changes_unlocked(ticks=ticks)

    @lt.action
    def increment_fprop2(self):
        self._fprop2 += 1

    @lt.action
    def increment_fprop2_unlocked(self):
        self._fprop2 += 1

    increment_fprop2_unlocked.use_global_lock = False

    @lt.action
    def increment_prop1(self):
        """This function is excluded from the lock - but prop1 is locked."""
        self.prop1 += 1

    increment_prop1.use_global_lock = False


def assert_can_change_property(thing: ConcurrencyChecker, name: str):
    """Check whether we can change a property of a Thing.

    :param thing: The ConcurrencyChecker instance being checked.
    :param name: The name of the property.
    :return: `True` if the property can be changed.
    """
    thing.changes_detected = False
    val = getattr(thing, name)  # read should always succeed
    setattr(thing, name, val + 1)
    thing.tick()
    assert thing.changes_detected is True


def assert_cannot_change_property(
    thing: ConcurrencyChecker, name: str, error: Exception = GlobalLockBusyError
):
    """Check whether we cannot change a property of a Thing.

    :param thing: The ConcurrencyChecker instance being checked.
    :param name: The name of the property.
    :return: `True` if setting the property raises an error.
    """
    thing.changes_detected = False
    val = getattr(thing, name)  # read should always succeed
    with pytest.raises(error):
        setattr(thing, name, val + 1)
    thing.tick()
    assert thing.changes_detected is False


def assert_action_makes_change(thing: ConcurrencyChecker, name: str):
    """Assert an action runs OK and causes properties to change."""
    thing.changes_detected = False
    action = getattr(thing, name)
    action()
    thing.tick()
    assert thing.changes_detected is True


def assert_action_fails(
    thing: ConcurrencyChecker, name: str, error: Exception = GlobalLockBusyError
):
    """Assert an action fails with an error and doesn't cause a change."""
    thing.changes_detected = False
    action = getattr(thing, name)
    with pytest.raises(error):
        action()
    thing.tick()
    assert thing.changes_detected is False


def lock_is_available(lock: GlobalLock) -> bool:
    """Check whether a lock is locked.

    This is needed for Python < 3.14 as there's no `locked` property.
    """
    checker = LockChecker(lock)
    checker.start()
    checker.join()
    return checker.acquired


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


def test_global_lock_with_thing():
    """Ensure the global lock stops multiple things happening at once."""
    thing = create_thing_without_server(ConcurrencyChecker, enable_global_lock=True)

    # Start the background action that checks for changes.
    monitor_thread = Thread(
        target=thing.check_for_changes_unlocked, kwargs={"ticks": 8}
    )
    monitor_thread.start()

    # When we are using the non-blocking checker, all the properties should work.
    for name in ["prop1", "prop2", "fprop1", "fprop2"]:
        assert_can_change_property(thing, name)

    # Increment actions should work too.
    for name in ["increment_fprop2", "increment_fprop2_unlocked", "increment_prop1"]:
        assert_action_makes_change(thing, name)

    assert monitor_thread.is_alive()
    thing.tick()
    monitor_thread.join()

    # Start the background action that checks for changes, and holds the lock
    monitor_thread = Thread(target=thing.check_for_changes_locked, kwargs={"ticks": 8})
    monitor_thread.start()

    # When we are holding the lock, by default properties can't be written.
    for name in ["prop1", "fprop1"]:
        assert_cannot_change_property(thing, name, GlobalLockBusyError)

    # The properties excluded from the lock may still be written
    for name in ["prop2", "fprop2"]:
        assert_can_change_property(thing, name)

    # By default, other actions won't run
    for name in ["increment_fprop2", "increment_prop1"]:
        assert_action_fails(thing, name, GlobalLockBusyError)

    # Actions may run if they're excluded from the lock.
    assert_action_makes_change(thing, "increment_fprop2_unlocked")

    assert monitor_thread.is_alive()
    thing.tick()
    monitor_thread.join()
