"""
This tests the log that is returned in an action invocation
"""

import logging
from fastapi.testclient import TestClient
import pytest
from ..temp_client import poll_task
import labthings_fastapi as lt
from labthings_fastapi.actions.invocation_model import LogRecordModel
from labthings_fastapi.logs import THING_LOGGER


pytestmark = pytest.mark.filterwarnings(
    "ignore:.*removed in v0.0.13.*:DeprecationWarning"
)


class ThingThatLogsAndErrors(lt.Thing):
    LOG_MESSAGES = [
        "message 1",
        "message 2",
    ]

    @lt.thing_action
    def action_that_logs(self, logger: lt.deps.InvocationLogger):
        for m in self.LOG_MESSAGES:
            logger.info(m)

    @lt.thing_action
    def action_with_unhandled_error(self, logger: lt.deps.InvocationLogger):
        raise RuntimeError("I was asked to raise this error.")

    @lt.thing_action
    def action_with_invocation_error(self, logger: lt.deps.InvocationLogger):
        raise lt.exceptions.InvocationError("This is an error, but I handled it!")


@pytest.fixture
def client():
    """Set up a Thing Server and yield a client to it."""
    server = lt.ThingServer({"log_and_error_thing": ThingThatLogsAndErrors})
    with TestClient(server.app) as client:
        yield client


def test_invocation_logging(caplog, client):
    """Check the expected items appear in the log when an action is invoked."""
    with caplog.at_level(logging.INFO, logger=THING_LOGGER.name):
        r = client.post("/log_and_error_thing/action_that_logs")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
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


def test_invocation_error_logs(caplog, client):
    """Check that expected errors are logged without a traceback."""
    with caplog.at_level(logging.INFO, logger=THING_LOGGER.name):
        r = client.post("/log_and_error_thing/action_with_invocation_error")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "error"
        assert len(invocation["log"]) == len(caplog.records) == 1
        assert caplog.records[0].levelname == "ERROR"
        # There is not a traceback
        assert caplog.records[0].exc_info is None


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
