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
from labthings_fastapi.invocation_contexts import (
    CancelEvent,
    ThreadWithInvocationID,
    cancellable_sleep,
    fake_invocation_context,
    get_cancel_event,
    get_invocation_id,
    invocation_id_ctx,
    raise_if_cancelled,
    set_invocation_id,
)
from labthings_fastapi.exceptions import (
    NoInvocationContextError,
    InvocationCancelledError,
)


def append_invocation_id(ids: list):
    """Append the current invocation ID (or the error) to a list."""
    try:
        ids.append(get_invocation_id())
    except NoInvocationContextError as e:
        ids.append(e)


def test_getting_and_setting_id():
    """Check the invocation context variable behaves as expected."""

    # By default, the invocation id is not set
    assert invocation_id_ctx.get(...) is ...

    # This means we get an error if we look for the ID
    with pytest.raises(NoInvocationContextError):
        get_invocation_id()

    # Once we set an ID, it should be returned
    id = uuid.uuid4()
    with set_invocation_id(id):
        assert get_invocation_id() == id

    # It should be reset afterwards
    with pytest.raises(NoInvocationContextError):
        get_invocation_id()

    # A context manager lets us fake the ID for testing
    with fake_invocation_context():
        assert isinstance(get_invocation_id(), uuid.UUID)

    # This should also be reset afterwards
    with pytest.raises(NoInvocationContextError):
        get_invocation_id()

    # A new thread will not copy the context by default, so using
    # get_invocation_id in a thread will fail:
    with fake_invocation_context():
        before = get_invocation_id()
        ids = []
        t = Thread(target=append_invocation_id, args=[ids])
        t.start()
        t.join()
        after = get_invocation_id()

        assert before == after
        assert len(ids) == 1
        assert isinstance(ids[0], NoInvocationContextError)


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
    event = CancelEvent.get_for_id(id)

    # We should get back the same event if we call this twice
    assert event is CancelEvent.get_for_id(id)
    # The function below is equivaent to the class method above.
    assert event is get_cancel_event(id)

    # We should not be able to make a second one with the constructor
    with pytest.raises(RuntimeError):
        CancelEvent(id)

    # We make a second event with a different ID. We'll use the constructor
    # directly, as this should work the first time it's called (as there is
    # no existing event).
    id2 = uuid.uuid4()
    event2 = CancelEvent(id2)
    assert event2 is CancelEvent.get_for_id(id2)
    assert event2 is not event
    assert get_cancel_event(id2) is event2

    # The module-level function falls back on the context variable for ID,
    # so it should raise an exception if the ID isn't present:
    with pytest.raises(NoInvocationContextError):
        get_cancel_event()

    # If we have an invocation ID in the context, this should succeed even
    # if we've not made an event yet.
    with fake_invocation_context():
        assert isinstance(get_cancel_event(), CancelEvent)

    # The two custom functions should raise `InvocationCancelledError` if
    # the event is set, so we'll run them both with it set and not set.
    # raise_if_set should do nothing if the event is not set.
    assert not event.is_set()
    event.raise_if_set()
    # it should raise an exception if the event is set.
    event.set()
    with pytest.raises(InvocationCancelledError):
        event.raise_if_set()
    # When the event raises an exception, it resets - one `set()` == one error.
    assert not event.is_set()

    # sleep behaves the same way, but waits a finite time.
    with assert_takes_time(0.02, 0.08):
        event.sleep(0.02)
    # check an exception gets raised and reset if appropriate
    event.set()
    with pytest.raises(InvocationCancelledError):
        event.sleep(1)
    assert not event.is_set()


def test_cancellable_sleep():
    """Check the module-level cancellable sleep."""
    # with no invocation context, the function should wait
    # and there should be no error.
    with assert_takes_time(0.02, 0.08):
        cancellable_sleep(0.02)

    with fake_invocation_context():
        event = get_cancel_event()

        # the function should wait a finite time
        with assert_takes_time(0.02, 0.08):
            cancellable_sleep(0.02)

        # check an exception gets raised and reset if appropriate
        event.set()
        with pytest.raises(InvocationCancelledError):
            cancellable_sleep(1)
        assert not event.is_set()


def test_raise_if_cancelled():
    """Check the module-level cancellable sleep."""
    # the function should return immediately.
    with assert_takes_time(None, 0.002):
        raise_if_cancelled()

    with fake_invocation_context():
        event = get_cancel_event()

        # the function should return immediately.
        with assert_takes_time(None, 0.002):
            raise_if_cancelled()

        # check an exception gets raised and reset if appropriate
        event.set()
        with pytest.raises(InvocationCancelledError):
            raise_if_cancelled()
        assert not event.is_set()


def test_thread_with_invocation_id():
    """Test our custom thread subclass makes a new ID and can be cancelled."""
    ids = []
    t = ThreadWithInvocationID(target=append_invocation_id, args=[ids])
    assert isinstance(t.invocation_id, uuid.UUID)
    t.start()
    t.join()
    assert len(ids) == 1
    assert ids[0] == t.invocation_id
    assert t.exception is None
    assert t.result is None


def test_thread_with_invocation_id_cancel():
    """Test the custom thread subclass responds to cancellation."""
    # Check cancellable sleep works in the thread
    t = ThreadWithInvocationID(target=cancellable_sleep, args=[1])
    assert isinstance(t.invocation_id, uuid.UUID)
    t.start()
    t.cancel()
    with assert_takes_time(None, 0.1):
        t.join()
    assert isinstance(t.exception, InvocationCancelledError)


def test_thread_with_invocation_id_return_value():
    """Check we capture the return value when running in a ThreadWithInvocationID."""
    t = ThreadWithInvocationID(target=lambda: True)
    t.start()
    t.join()
    assert t.exception is None
    assert t.result is True


def run_function_in_thread_and_propagate_cancellation(func, *args):
    """Run a function in a ThreadWithInvocationID."""
    t = ThreadWithInvocationID(target=func, args=args)
    t.start()
    try:
        t.join_and_propagate_cancel(1)
    except InvocationCancelledError:
        # We still want to return the finished thread if it's
        # cancelled.
        pass
    return t


def test_thread_with_invocation_id_cancellation_propagates():
    """Check that a cancel event can propagate to our thread.

    ``join_and_propagate_cancellation`` should cancel the spawned thread if
    the parent thread is cancelled while it's waiting for the spawned thread
    to join.
    """
    # Check we can propagate cancellation.
    # First, we run `cancellable_sleep` and check it doesn't cancel
    with fake_invocation_context():
        # First test our function - there is only one thread here, and we
        # check it finishes and doesn't error.
        t = run_function_in_thread_and_propagate_cancellation(cancellable_sleep, 0.02)
        assert isinstance(t, ThreadWithInvocationID)
        assert not t.is_alive()
        assert t.exception is None

        # Next, we run it in a thread, and cancel that thread.
        # The error should propagate to the inner thread.
        t = ThreadWithInvocationID(
            target=run_function_in_thread_and_propagate_cancellation,
            args=[cancellable_sleep, 10],
        )
        t.start()
        t.cancel()
        with assert_takes_time(None, 0.08):
            t.join()
        assert isinstance(t.result, ThreadWithInvocationID)
        assert isinstance(t.result.exception, InvocationCancelledError)
