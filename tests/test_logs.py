"""Unit tests for the `.logs` module.

These tests are intended to complement the more functional tests
in ``test_action_logging`` with bottom-up tests for code in the
`.logs` module.
"""

from collections import deque
import logging
from types import EllipsisType
import pytest
from uuid import UUID, uuid4
from labthings_fastapi import logs
from labthings_fastapi.invocation_contexts import (
    fake_invocation_context,
    set_invocation_id,
)
import labthings_fastapi as lt
from labthings_fastapi.exceptions import LogConfigurationError
from labthings_fastapi.thing_server_interface import create_thing_without_server


class ThingThatLogs(lt.Thing):
    @lt.thing_action
    def log_a_message(self, msg: str):
        """Log a message to the thing's logger."""
        self.logger.info(msg)


def reset_thing_logger():
    """Remove all handlers from the THING_LOGGER to reset it."""
    logger = logs.THING_LOGGER
    # Note that the [:] below is important: this copies the list and avoids
    # issues with modifying a list as we're iterating through it.
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    for f in logger.filters[:]:
        logger.removeFilter(f)
    assert len(logger.handlers) == 0
    assert len(logger.filters) == 0


def make_record(msg="A test message", id: UUID | EllipsisType | None = ...):
    """A LogRecord object."""
    record = logging.LogRecord(
        "labthings_fastapi.things.test",
        logging.INFO,
        "test/file/path.py",
        42,
        msg,
        None,
        None,
        "test_function",
        None,
    )
    if id is not ...:
        record.invocation_id = id
    return record


def test_inject_invocation_id_nocontext():
    """Check our filter function correctly adds invocation ID to a log record."""
    record = make_record()
    # The record won't have an invocation ID to start with.
    assert not hasattr(record, "invocation_id")
    # The filter should return True (to keep the record)
    assert logs.inject_invocation_id(record) is True
    # It should add the attribute, but with no invocation
    # context, it should be set to None
    assert record.invocation_id is None

    # Currently, if we re-run the filter it silently overwrites,
    # so there should be no error below:
    assert logs.inject_invocation_id(record) is True

    # Currently, it should overwrite the value. This behaviour
    # possibly wants to change in the future, and this test
    # should be updated.
    with fake_invocation_context() as id:
        assert logs.inject_invocation_id(record) is True
    assert record.invocation_id == id


def test_inject_invocation_id_withcontext():
    """Check our filter function correctly adds invocation ID to a log record."""
    record = make_record()
    # The record won't have an invocation ID to start with.
    assert not hasattr(record, "invocation_id")
    # The filter should return True (to keep the record)
    with fake_invocation_context() as id:
        assert logs.inject_invocation_id(record) is True
    assert record.invocation_id == id

    # Currently, it should overwrite the value. This behaviour
    # possibly wants to change in the future, and this test
    # should be updated. This ID should be a fresh one.
    with fake_invocation_context() as id2:
        assert logs.inject_invocation_id(record) is True
    # Check the ID has changed and was overwritten.
    assert id2 != id
    assert record.invocation_id == id2


def test_dequebyinvocationidhandler():
    """Check the custom log handler works as expected."""
    handler = logs.DequeByInvocationIDHandler()
    assert handler.level == logging.INFO

    destinations = {
        uuid4(): deque(),
        uuid4(): deque(),
    }
    # We should be able to log with nothing set up, the record
    # won't go anywhere but there shouldn't be any errors.
    for id in destinations.keys():
        handler.emit(make_record(id=id))
    for dest in destinations.values():
        assert len(dest) == 0

    # After adding the destinations, the logs should appear.
    for id, dest in destinations.items():
        handler.add_destination_for_id(id, dest)

    for id in destinations.keys():
        handler.emit(make_record(id=id))
    for id, dest in destinations.items():
        assert len(dest) == 1
        assert dest[0].invocation_id == id


def test_configure_thing_logger():
    """Check the logger is configured correctly."""
    # Start by resetting the handlers on the logger
    reset_thing_logger()

    # Then configure it
    logs.configure_thing_logger()

    # Check it's correct
    assert logs.THING_LOGGER.level == logging.INFO
    assert len(logs.THING_LOGGER.handlers) == 1
    assert isinstance(logs.THING_LOGGER.handlers[0], logs.DequeByInvocationIDHandler)

    # Test it out
    with fake_invocation_context() as id:
        dest = deque()
        logs.add_thing_log_destination(id, dest)
        logger = logs.THING_LOGGER.getChild("foo")
        logger.info("Test")
        assert len(dest) == 1
        assert dest[0].msg == "Test"


def test_add_thing_log_destination():
    """Check the module-level function to add an invocation log destination."""
    reset_thing_logger()
    id = uuid4()
    dest = deque()

    with pytest.raises(LogConfigurationError):
        # This won't work until the handler is added
        logs.add_thing_log_destination(id, dest)

    logs.THING_LOGGER.addHandler(logs.DequeByInvocationIDHandler())
    logs.THING_LOGGER.addHandler(logs.DequeByInvocationIDHandler())
    with pytest.raises(LogConfigurationError):
        # More than one handler will also make it fail with an error.
        logs.add_thing_log_destination(id, dest)

    reset_thing_logger()
    logs.configure_thing_logger()

    thing = create_thing_without_server(ThingThatLogs)
    logs.add_thing_log_destination(id, dest)
    with set_invocation_id(id):
        thing.log_a_message("Test Message.")
    assert len(dest) == 1
    assert dest[0].getMessage() == "Test Message."
