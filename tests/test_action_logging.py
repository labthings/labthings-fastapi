"""
This tests the log that is returned in an action invocation
"""

import logging

import pytest

import labthings_fastapi as lt
from labthings_fastapi.invocations import LogRecordModel
from labthings_fastapi.logs import THING_LOGGER

from .temp_client import poll_task


class ThingThatLogsAndErrors(lt.Thing):
    LOG_MESSAGES = [
        "message 1",
        "message 2",
    ]

    @lt.action
    def action_that_logs(self):
        for m in self.LOG_MESSAGES:
            self.logger.info(m)

    @lt.action
    def action_with_unhandled_error(self):
        raise RuntimeError("I was asked to raise this error.")

    @lt.action
    def action_with_invocation_error(self):
        raise lt.exceptions.InvocationError("This is an error, but I handled it!")


@pytest.fixture
def client():
    """Set up a Thing Server and yield a client to it."""
    server = lt.ThingServer.from_things({"log_and_error_thing": ThingThatLogsAndErrors})
    with server.test_client() as client:
        yield client


def test_invocation_logging(caplog, client):
    """Check the expected items appear in the log when an action is invoked."""
    with caplog.at_level(logging.INFO, logger=THING_LOGGER.name):
        r = client.post("/log_and_error_thing/action_that_logs")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert len(caplog.records) == len(ThingThatLogsAndErrors.LOG_MESSAGES)
        assert len(invocation["log"]) == len(ThingThatLogsAndErrors.LOG_MESSAGES)
        assert len(invocation["log"]) == len(caplog.records)
        for expected, entry in zip(
            ThingThatLogsAndErrors.LOG_MESSAGES, invocation["log"], strict=True
        ):
            assert entry["message"] == expected


def test_unhandled_error_logs(caplog, client):
    """Check that a log with a traceback is raised if there is an unhandled error."""
    with caplog.at_level(logging.INFO, logger=THING_LOGGER.name):
        r = client.post("/log_and_error_thing/action_with_unhandled_error")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "error"
        assert len(invocation["log"]) == len(caplog.records) == 1
        assert caplog.records[0].levelname == "ERROR"
        # There is a traceback
        assert caplog.records[0].exc_info is not None
        # Check the "error" property is populated correctly.
        problem_details = invocation["error"]
        assert isinstance(problem_details, dict)
        assert problem_details == {
            "type": "https://docs.python.org/3/library/exceptions.html#RuntimeError",
            "detail": "I was asked to raise this error.",
            "title": "RuntimeError",
            "status": 500,  # this is the default status
            "instance": None,
        }


def test_invocation_error_logs(caplog, client):
    """Check that a log with a traceback is raised if there is an unhandled error."""
    with caplog.at_level(logging.INFO, logger=THING_LOGGER.name):
        r = client.post("/log_and_error_thing/action_with_invocation_error")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "error"
        assert len(invocation["log"]) == len(caplog.records) == 1
        assert caplog.records[0].levelname == "ERROR"
        # There is not a traceback
        assert caplog.records[0].exc_info is None
        # Check the "error" property is populated correctly.
        problem_details = invocation["error"]
        assert isinstance(problem_details, dict)
        assert problem_details == {
            "type": (
                "https://labthings-fastapi.readthedocs.io/en/latest/autoapi/"
                "labthings_fastapi/exceptions/index.html#labthings_fastapi."
                "exceptions.InvocationError"
            ),
            "detail": "This is an error, but I handled it!",
            "title": "InvocationError",
            "status": 500,  # this is the default status
            "instance": None,
        }


def test_logrecordmodel():
    record = logging.LogRecord(
        name="recordName",
        level=logging.INFO,
        pathname="dummy/path",
        lineno=0,
        msg="a string message",
        args=None,
        exc_info=None,
    )
    m = LogRecordModel.model_validate(record, from_attributes=True)
    assert m.levelname == record.levelname


def test_logrecord_args():
    record = logging.LogRecord(
        name="recordName",
        level=logging.INFO,
        pathname="dummy/path",
        lineno=0,
        msg="mambo number %d",
        args=(5,),
        exc_info=None,
    )
    m = LogRecordModel.model_validate(record, from_attributes=True)
    assert m.message == record.getMessage()


def test_logrecord_too_many_args():
    """Calling getMessage() will raise an error - but it should still validate

    If it doesn't validate, it will cause every subsequent call to the action's
    invocation record to return a 500 error.
    """
    record = logging.LogRecord(
        name="recordName",
        level=logging.INFO,
        pathname="dummy/path",
        lineno=0,
        msg="mambo number %d",
        args=(5, 6),
        exc_info=None,
    )
    m = LogRecordModel.model_validate(record, from_attributes=True)
    assert m.message.startswith("Error")
