"""Test logging and cancellation, implemented via contextvars.

These tests cover the code in `invocation_contexts` directly. They are also tested
in the context of a ``ThingServer`` in, for example, ``test_action_logging`` and
``test_action_cancel`` .
"""

from contextlib import contextmanager
import time
import pytest
import uuid
from threading import Thread
from labthings_fastapi import invocation_contexts as ic
from labthings_fastapi import exceptions as exc


def append_invocation_id(ids: list):
    """Append the current invocation ID (or the error) to a list."""
    try:
        ids.append(ic.get_invocation_id())
    except exc.NoInvocationContextError as e:
        ids.append(e)


def test_getting_and_setting_id():
    """Check the invocation context variable behaves as expected."""

    # By default, the invocation id is not set
    assert ic.invocation_id_ctx.get(...) is ...

    # This means we get an error if we look for the ID
    with pytest.raises(exc.NoInvocationContextError):
        ic.get_invocation_id()

    # Once we set an ID, it should be returned
    id = uuid.uuid4()
    with ic.set_invocation_id(id):
        assert ic.get_invocation_id() == id

    # It should be reset afterwards
    with pytest.raises(exc.NoInvocationContextError):
        ic.get_invocation_id()

    # A context manager lets us fake the ID for testing
    with ic.fake_invocation_context():
        assert isinstance(ic.get_invocation_id(), uuid.UUID)

    # This should also be reset afterwards
    with pytest.raises(exc.NoInvocationContextError):
        ic.get_invocation_id()

    # A new thread will not copy the context by default, so using
    # get_invocation_id in a thread will fail:
    with ic.fake_invocation_context():
        before = ic.get_invocation_id()
        ids = []
        t = Thread(target=append_invocation_id, args=[ids])
        t.start()
        t.join()
        after = ic.get_invocation_id()

        assert before == after
        assert len(ids) == 1
        assert isinstance(ids[0], exc.NoInvocationContextError)


@contextmanager
def assert_takes_time(min_t: float | None, max_t: float | None):
    """Assert that a code block takes a certain amount of time."""
    before = time.time()
    yield
    after = time.time()
    duration = after - before
    if min_t is not None:
        assert duration >= min_t
    if max_t is not None:
        assert duration <= max_t


def test_cancel_event():
    """Check the cancel event works as intended."""
    id = uuid.uuid4()
    event = ic.CancelEvent.get_for_id(id)

    # We should get back the same event if we call this twice
    assert event is ic.CancelEvent.get_for_id(id)
    # The function below is equivaent to the class method above.
    assert event is ic.get_cancel_event(id)

    # We should not be able to make a second one with the constructor
    with pytest.raises(RuntimeError):
        ic.CancelEvent(id)

    # We make a second event with a different ID. We'll use the constructor
    # directly, as this should work the first time it's called (as there is
    # no existing event).
    id2 = uuid.uuid4()
    event2 = ic.CancelEvent(id2)
    assert event2 is ic.CancelEvent.get_for_id(id2)
    assert event2 is not event
    assert ic.get_cancel_event(id2) is event2

    # The module-level function falls back on the context variable for ID,
    # so it should raise an exception if the ID isn't present:
    with pytest.raises(exc.NoInvocationContextError):
        ic.get_cancel_event()

    # If we have an invocation ID in the context, this should succeed even
    # if we've not made an event yet.
    with ic.fake_invocation_context():
        assert isinstance(ic.get_cancel_event(), ic.CancelEvent)

    # The two custom functions should raise `InvocationCancelledError` if
    # the event is set, so we'll run them both with it set and not set.
    # raise_if_set should do nothing if the event is not set.
    assert not event.is_set()
    event.raise_if_set()
    # it should raise an exception if the event is set.
    event.set()
    with pytest.raises(exc.InvocationCancelledError):
        event.raise_if_set()
    # When the event raises an exception, it resets - one `set()` == one error.
    assert not event.is_set()

    # sleep behaves the same way, but waits a finite time.
    with assert_takes_time(0.02, 0.04):
        event.sleep(0.02)
    # check an exception gets raised and reset if appropriate
    event.set()
    with pytest.raises(exc.InvocationCancelledError):
        event.sleep(1)
    assert not event.is_set()


def test_cancellable_sleep():
    """Check the module-level cancellable sleep."""
    with pytest.raises(exc.NoInvocationContextError):
        ic.cancellable_sleep(1)
    with pytest.raises(exc.NoInvocationContextError):
        ic.cancellable_sleep(None)

    with ic.fake_invocation_context():
        event = ic.get_cancel_event()

        # the function should wait a finite time
        with assert_takes_time(0.02, 0.04):
            ic.cancellable_sleep(0.02)

        # passing `None` should return immediately.
        with assert_takes_time(None, 0.002):
            ic.cancellable_sleep(None)

        # check an exception gets raised and reset if appropriate
        event.set()
        with pytest.raises(exc.InvocationCancelledError):
            ic.cancellable_sleep(1)
        assert not event.is_set()

        # check an exception gets raised and reset if appropriate
        event.set()
        with pytest.raises(exc.InvocationCancelledError):
            ic.cancellable_sleep(None)
        assert not event.is_set()


def test_invocation_logger():
    """Check `get_invocation_logger` behaves correctly."""
    # The function simply returns a logger with the ID in the name.
    fake_id = uuid.uuid4()
    logger = ic.get_invocation_logger(fake_id)
    assert logger.name.endswith(str(fake_id))

    # The ID is taken from context if not supplied.
    with pytest.raises(exc.NoInvocationContextError):
        ic.get_invocation_logger()
    with ic.fake_invocation_context():
        logger = ic.get_invocation_logger()
        id = ic.get_invocation_id()
        assert logger.name.endswith(str(id))


def run_function_in_thread_and_propagate_cancellation(func, *args):
    """Run a function in a ThreadWithInvocationID."""
    t = ic.ThreadWithInvocationID(target=func, args=args)
    t.start()
    try:
        t.join_and_propagate_cancel(0.005)
    except exc.InvocationCancelledError:
        # We still want to return the finished thread if it's
        # cancelled.
        pass
    return t


def test_thread_with_invocation_id():
    """Test our custom thread subclass makes a new ID and can be cancelled."""
    ids = []
    t = ic.ThreadWithInvocationID(target=append_invocation_id, args=[ids])
    assert isinstance(t.invocation_id, uuid.UUID)
    t.start()
    t.join()
    assert len(ids) == 1
    assert ids[0] == t.invocation_id
    assert t.exception is None
    assert t.result is None

    # Check cancellable sleep works in the thread
    t = ic.ThreadWithInvocationID(target=ic.cancellable_sleep, args=[1])
    assert isinstance(t.invocation_id, uuid.UUID)
    t.start()
    t.cancel()
    with assert_takes_time(None, 0.1):
        t.join()
    assert isinstance(t.exception, exc.InvocationCancelledError)

    # Check we capture the return value
    t = ic.ThreadWithInvocationID(target=lambda: True)
    t.start()
    t.join()
    assert t.exception is None
    assert t.result is True

    # Check we can propagate cancellation.
    # First, we run `cancellable_sleep` and check it doesn't cancel
    with ic.fake_invocation_context():
        # First test our function - there is only one thread here, and we
        # check it finishes and doesn't error.
        t = run_function_in_thread_and_propagate_cancellation(
            ic.cancellable_sleep, 0.001
        )
        assert isinstance(t, ic.ThreadWithInvocationID)
        assert not t.is_alive()
        assert t.exception is None

        # Next, we run it in a thread, and cancel that thread.
        # The error should propagate to the inner thread.
        t = ic.ThreadWithInvocationID(
            target=run_function_in_thread_and_propagate_cancellation,
            args=[ic.cancellable_sleep, 10],
        )
        t.start()
        t.cancel()
        with assert_takes_time(None, 0.05):
            t.join()
        assert isinstance(t.result, ic.ThreadWithInvocationID)
        assert isinstance(t.result.exception, exc.InvocationCancelledError)
