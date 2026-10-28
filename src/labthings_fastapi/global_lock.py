"""Global locking.

If the feature is enabled, a global lock is used to restrict running actions
and setting properties. This module defines a wrapper for `threading.RLock`
with a context manager that acquires the lock using a short timeout.
"""

from threading import RLock
from types import EllipsisType, TracebackType

from labthings_fastapi.exceptions import GlobalLockBusyError


class GlobalLock:
    """An RLock wrapper and work-a-like with a default timeout."""

    def __init__(self) -> None:
        """Initialise the global lock."""
        self._lock = RLock()

    default_timeout: float = 0.05

    def acquire(
        self, blocking: bool = True, timeout: float | EllipsisType = ...
    ) -> bool:
        """Acquire the lock.

        This wraps the underlying `threading.RLock.acquire` but will by default
        block with a short timeout.

        :param blocking: whether to wait for the lock to become free. `True` (the
            default) will block until the lock is available or we time out. `False`
            will always return immediately.
        :param timeout: the length of time to wait for the lock, if ``blocking`` is
            `True` - or `-1` to specify waiting forever.

        :return: whether the lock was successfully acquired.
        """
        if blocking is False:
            return self._lock.acquire(blocking=False)
        if timeout is ...:
            timeout = self.default_timeout
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        """Release the lock.

        This wraps `threading.RLock.release` without modification.
        """
        self._lock.release()

    def __enter__(self) -> None:
        """Allow the lock to be used as a context manager.

        The behaviour when used as a context manager is different from a regular
        `threading.RLock` because it will use the default timeout rather than
        blocking forever.

        :raises GlobalLockBusyError: if the lock is in use by another thread.
        """
        result = self.acquire(blocking=True, timeout=self.default_timeout)
        if not result:
            raise GlobalLockBusyError("The global lock could not be acquired.")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Allow the lock to be used as a context manager.

        The lock is released when the context ends. No error handling is done.

        :param exc_type: the exception type, if one was raised (ignored).
        :param exc_value: the exception, if one was raised (ignored).
        :param traceback: the traceback, if an error was raised (ignored).
        """
        self.release()
