"""Test code for the global lock."""

from threading import Thread, Event
from labthings_fastapi.exceptions import GlobalLockBusyError
import pytest

from labthings_fastapi.global_lock import GlobalLock

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
