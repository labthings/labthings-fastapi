"""
This tests the log that is returned in an action invocation
"""

import logging
from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer
from temp_client import poll_task
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.dependencies.invocation import InvocationLogger
from labthings_fastapi.actions.invocation_model import LogRecordModel


class ThingOne(Thing):
    LOG_MESSAGES = [
        "message 1",
        "message 2",
    ]

    @thing_action
    def action_one(self, logger: InvocationLogger):
        for m in self.LOG_MESSAGES:
            logger.info(m)


def test_invocation_logging(caplog):
    caplog.set_level(logging.INFO)
    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one")
    with TestClient(server.app) as client:
        r = client.post("/thing_one/action_one")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert len(invocation["log"]) == len(ThingOne.LOG_MESSAGES)
        for expected, entry in zip(ThingOne.LOG_MESSAGES, invocation["log"]):
            assert entry["message"] == expected


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
