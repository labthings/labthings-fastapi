r"""Invocation-specific resources provided via context.

This module provides key resources to code that runs as part of an action,
specifically a mechanism to allow cancellation, and a way to manage logging.
These replace the old dependencies ``CancelHook`` and ``InvocationLogger``\ .

If you are writing action code and want to use logging or allow cancellation,
most of the time you should just use `.get_invocation_logger` or
`.cancellable_sleep` which are exposed as part of the top-level module.

This module includes lower-level functions that are useful for testing or
managing concurrency. Many of these accept an ``id`` argument, which is
optional. If it is not supplied, we will use the context variables to find
the current invocation ID.
"""

from collections.abc import Iterator, Mapping, Sequence
from contextvars import ContextVar
from contextlib import contextmanager
import logging
from threading import Event, Thread
from typing import Any, Callable
from typing_extensions import Self
from uuid import UUID, uuid4
from weakref import WeakValueDictionary

from .exceptions import InvocationCancelledError, NoInvocationContextError


invocation_id_ctx = ContextVar[UUID]("invocation_id_ctx")
"""Context variable storing the current invocation ID.

Note that it is best not to access this directly. Using `.set_invocation_id`
is safer, as it ensures proper clean-up and continuity of the cancel event
associated with the invocation.
"""


def get_invocation_id() -> UUID:
    """Return the current InvocationID.

    This function returns the ID of the current invocation. This is determined
    from execution context: it will only succeed if it is called from an action
    thread.

    If this function is called outside of an action thread, it will raise
    an error.

    :return: the invocation ID of the current invocation.
    :raises NoInvocationContextError: if called outside of an action thread.
    """
    try:
        return invocation_id_ctx.get()
    except LookupError as e:
        msg = "There is no invocation ID to return: this code was called from "
        msg += "outside of an action thread."
        raise NoInvocationContextError(msg) from e


@contextmanager
def set_invocation_id(id: UUID) -> Iterator[None]:
    """Set the invocation ID associated with the current context.

    This is the preferred way to create a new invocation context. As well
    as setting and cleaning up the invocation ID context variable, this
    context manager ensures that the cancellation event persists and is
    not accidentally reset because it's gone out of scope.

    :param id: The invocation ID to save in the context variable.
    """
    token = invocation_id_ctx.set(id)
    event = get_cancel_event(id)
    try:
        yield
    finally:
        invocation_id_ctx.reset(token)
        del event


@contextmanager
def fake_invocation_context() -> Iterator[UUID]:
    """Set a dummy invocation ID for a block of code.

    This function should be used in a ``with:`` block.

    :yields: the created invocation ID.
    """
    id = uuid4()
    with set_invocation_id(id):
        yield id


class CancelEvent(Event):
    """An Event subclass that enables cancellation of actions.

    This `threading.Event` subclass adds methods to raise
    `.InvocationCancelledError` exceptions if the invocation is cancelled,
    usually by a ``DELETE`` request to the invocation's URL.
    """

    _cancel_events: WeakValueDictionary[UUID, Self] = WeakValueDictionary()
    "This class-level dictionary ensures only one event exists per invocation ID"

    def __init__(self, id: UUID) -> None:
        """Initialise a cancellation event.

        Only one CancelEvent should exist per invocation. Trying to create a
        second will raise an error. To avoid this, please use
        `.CancelEvent.get_for_id` instead of the constructor.

        :param id: The invocation ID.
        :raises RuntimeError: if a `.CancelEvent` has already been created for
            the specified invocation ID.
        """
        super().__init__()
        self.invocation_id = id
        if id in self.__class__._cancel_events:
            msg = f"Tried to create a second CancelEvent for invocation {id}. "
            msg += "Use `CancelEvent.get_for_id` to avoid this error."
            raise RuntimeError(msg)
        self.__class__._cancel_events[id] = self

    @classmethod
    def get_for_id(cls, id: UUID) -> Self:
        """Obtain the `.CancelEvent` for a particular Invocation ID.

        This is a safe way to obtain an instance of this class, though
        the top-level function `.get_cancel_event` is recommended.

        Only one `.CancelEvent` should exist per Invocation. This method
        will either create one, or return the existing one.

        :param id: The invocation ID.
        :return: the cancel event for the given ``id`` .
        """
        try:
            return cls._cancel_events[id]
        except KeyError:
            return cls(id)

    def raise_if_set(self) -> None:
        """Raise an exception if the event is set.

        An exception will be raised if the event has been set.
        Before raising the exception, we clear the event. This means that setting
        the event should raise exactly one exception, and that handling the exception
        should result in the action continuing to run.

        This is intended as a compact alternative to:

        .. code-block::

            if cancel_event.is_set():
                cancel_event.clear()
                raise InvocationCancelledError()

        :raise InvocationCancelledError: if the event has been cancelled.
        """
        if self.is_set():
            self.clear()
            raise InvocationCancelledError("The action was cancelled.")

    def sleep(self, timeout: float) -> None:
        r"""Sleep for a given time in seconds, but raise an exception if cancelled.

        This function can be used in place of `time.sleep`. It will usually behave
        the same as `time.sleep`\ , but if the cancel event is set during the time
        when we are sleeping, an exception is raised to interrupt the sleep and
        cancel the action. The event is cleared before raising the exception. This
        means that handling the exception is sufficient to allow the action to
        continue.

        :param timeout: The time to sleep for, in seconds.

        :raise InvocationCancelledError: if the event has been cancelled.
        """
        if self.wait(timeout):
            self.clear()
            raise InvocationCancelledError("The action was cancelled.")


def get_cancel_event(id: UUID | None = None) -> CancelEvent:
    """Obtain an event that permits actions to be cancelled.

    :param id: The invocation ID. This will be determined from
        context if not supplied.
    :return: an event that allows the current invocation to be cancelled.
    """
    if id is None:
        id = get_invocation_id()
    return CancelEvent.get_for_id(id)


def cancellable_sleep(interval: float | None) -> None:
    """Sleep for a specified time, allowing cancellation.

    This function should be called from action functions instead of
    `time.sleep` to allow them to be cancelled. Usually, this
    function is equivalent to `time.sleep` (it waits the specified
    number of seconds). If the action is cancelled during the sleep,
    it will raise an `.InvocationCancelledError` to signal that the
    action should finish.

    .. warning::

        This function uses `.Event.wait` internally, which suffers
        from timing errors on some platforms: it may have error of
        around 10-20ms. If that's a problem, consider using
        `time.sleep` instead. ``lt.cancellable_sleep(None)`` may then
        be used to allow cancellation.

    This function may only be called from an action thread, as it
    depends on the invocation ID being available from a context variable.
    Use `.set_invocation_id` to make it available outside of an action
    thread.

    If ``interval`` is set to None, we do not call `.Event.wait` but
    instead we simply check whether the event is set.

    :param interval: The length of time to sleep for, in seconds. If it
        is `None` we won't wait, but we will still check for a cancel
        event, and raise the exception if it is set.
    """
    event = get_cancel_event()
    if interval is None:
        event.raise_if_set()
    else:
        event.sleep(interval)


def get_invocation_logger(id: UUID | None = None) -> logging.Logger:
    """Obtain a logger for the current invocation.

    Use this function to get a logger to use in action code. This
    will associate the log messages with the invocation, so that
    they may be used as status updates or related to a particular run
    of the action.

    :param id: the invocation ID. This will be determined from context
        so need not be specified in action code.
    :return: a logger that is specific to a particular invocation of
        an action.
    """
    if id is None:
        id = get_invocation_id()
    logger = logging.getLogger(f"labthings_fastapi.actions.{id}")
    return logger


class ThreadWithInvocationID(Thread):
    r"""A thread that sets a new invocation ID.

    This is a subclass of `threading.Thread` and works very much the
    same way. It implements its functionality by overriding the ``run``
    method, so this should not be overridden again - you should instead
    specify the code to run using the ``target`` argument.

    This function enables an action to be run in a thread, which gets its
    own invocation ID and cancel hook. This means logs will not be interleaved
    with the calling action, and the thread may be cancelled just like an
    action started over HTTP, by calling its ``cancel`` method.

    The thread also remembers the return value of the target function
    in the property ``result`` and stores any exception raised in the
    ``exception`` property.

    A final LabThings-specific feature is cancellation propagation. If
    the thread is started from an action that may be cancelled, it may
    be joined with ``join_and_propagate_cancel``\ . This is intended
    to be equivalent to calling ``join`` but with the added feature that,
    if the parent thread is cancelled while waiting for the child thread
    to join, the child thread will also be cancelled.
    """

    def __init__(
        self,
        target: Callable,
        args: Sequence[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
        *super_args: Any,
        **super_kwargs: Any,
    ) -> None:
        r"""Initialise a thread with invocation ID.

        :param target: the function to call in the thread.
        :param args: positional arguments to ``target``\ .
        :param kwargs: keyword arguments to ``target``\ .
        :param \*super_args: arguments passed to `threading.Thread`\ .
        :param \*\*super_kwargs: keyword arguments passed to `threading.Thread`\ .
        """
        super().__init__(*super_args, **super_kwargs)
        self._target = target
        self._args = args or []
        self._kwargs = kwargs or {}
        self._invocation_id: UUID = uuid4()
        self._result: Any = None
        self._exception: BaseException | None = None

    @property
    def invocation_id(self) -> UUID:
        """The InvocationID of this thread."""
        return self._invocation_id

    @property
    def result(self) -> Any:
        """The return value of the target function."""
        return self._result

    @property
    def exception(self) -> BaseException | None:
        """The exception raised by the target function, or None."""
        return self._exception

    def cancel(self) -> None:
        """Set the cancel event to tell the code to terminate."""
        get_cancel_event(self.invocation_id).set()

    def join_and_propagate_cancel(self, poll_interval: float = 0.2) -> None:
        """Wait for the thread to finish, and propagate cancellation.

        This function wraps `threading.Thread.join` but periodically checks if
        the calling thread has been cancelled. If it has, it will cancel the
        thread, before attempting to ``join`` it again.

        Note that, if the invocation that calls this function is cancelled
        while the function is running, the exception will propagate, i.e.
        you should handle `.InvocationCancelledError` unless you wish
        your invocation to terminate if it is cancelled.

        :param poll_interval: How often to check for cancellation of the
            calling thread, in seconds.
        :raises InvocationCancelledError: if this invocation is cancelled
            while waiting for the thread to join.
        """
        cancellation: InvocationCancelledError | None = None
        self._polls = 0
        self._attempted_cancels = 0
        print(f"Checking for cancellation of invocation {get_invocation_id()}")
        print(f"so we can cancel {self.invocation_id}")
        while self.is_alive():
            try:
                cancellable_sleep(None)
                self._polls += 1
            except InvocationCancelledError as e:
                # Propagate the cancellation signal to the thread
                cancellation = e
                self.cancel()
                self._attempted_cancels += 1
            self.join(timeout=poll_interval)
        if cancellation is not None:
            # If the action was cancelled, propagate the cancellation
            # after the thread has been joined.
            # Note that, regardless of how many times the thread was
            # cancelled, we will only raise one exception after the
            # calling thread was joined.
            raise InvocationCancelledError() from cancellation

    def run(self) -> None:
        """Run the target function, with invocation ID set in the context variable."""
        try:
            with set_invocation_id(self.invocation_id):
                if self._target is not None:
                    self._result = self._target(*self._args, **self._kwargs)
        except BaseException as e:  # noqa: BLE001
            # This catch-all Except allows us to access exceptions
            # in the parent thread
            self._exception = e
        finally:
            # Avoid a refcycle if the thread is running a function with
            # an argument that has a member that points to the thread.
            del self._target, self._args, self._kwargs
