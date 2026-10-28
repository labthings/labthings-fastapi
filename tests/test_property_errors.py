"""Test how errors in property getters/setters are handled.

This test file is intended to check the error handling code dealing with properties.
Errors in property getter/setter code should result in helpful HTTP errors and
Python exceptions. This test module is intended to check that various error
conditions result in easily-interpreted exceptions, log entries, and HTTP responses.
"""

import logging

import pytest

import labthings_fastapi as lt
from labthings_fastapi.exceptions import ClientPropertyError
from labthings_fastapi.testing import create_thing_without_server


class SpecificError(RuntimeError):
    """A specific error class we can test for."""


class ErrorThing(lt.Thing):
    """A Thing that has properties with a variety of failure modes."""

    @lt.property
    def always_raises(self) -> int:
        """An integer that errors on get and set."""
        raise SpecificError("'always_raises' failed, as expected.")

    @always_raises.setter
    def _set_always_raises(self, value: int) -> None:
        raise SpecificError("'always_raises' failed, as expected.")

    @always_raises.resetter
    def _reset_always_raises(self) -> None:
        raise SpecificError("'always_raises' failed, as expected.")

    @lt.property
    def wrongly_typed(self) -> int:
        """A value of the wrong type."""
        return "not an integer"

    @lt.property
    def violates_constraint(self) -> int:
        """An integer that's outside the allowed range."""
        return 42

    violates_constraint.constraints = {"le": 10}


@pytest.fixture
def thing():
    """A fixture returning an instance of ErrorThing."""
    return create_thing_without_server(ErrorThing)


@pytest.fixture
def client():
    """A fixture returning a ThingClient for an ErrorThing."""
    server = lt.ThingServer.from_things({"thing": ErrorThing})
    with server.test_client() as tc:
        return lt.ThingClient.from_url("/thing/", client=tc)


# The functions below check errors when called directly from Python


def test_get_always_raises_python(thing: ErrorThing):
    """Check always_raises errors when retrieved directly."""
    with pytest.raises(SpecificError, match="failed, as expected"):
        _ = thing.always_raises


def test_set_always_raises_python(thing: ErrorThing):
    """Check always_raises errors when set directly."""
    with pytest.raises(SpecificError, match="failed, as expected"):
        thing.always_raises = 42


def test_reset_always_raises_python(thing: ErrorThing):
    """Check always_raises errors when reset."""
    with pytest.raises(SpecificError, match="failed, as expected"):
        thing.properties["always_raises"].reset()


def test_wrongly_typed_python(thing: ErrorThing):
    """Check we can retrieve a wrongly typed value in Python."""
    # Currently, no validation is performed on property values
    # when they are retrieved from Python
    assert thing.wrongly_typed == "not an integer"


def test_violates_constraint_python(thing: ErrorThing):
    """Check we can retrieve a value in Python that violates its constraint."""
    assert thing.violates_constraint == 42


# The next section tests the same conditions as the previous one, but in the
# context of a server.
# Typing note: `client` is type hinted as an ErrorThing as it should have an
# equivalent signature. This is largely to enable static analysis in editors.
# It is actually a `lt.ThingClient` instance.


def test_get_always_raises_server(client: ErrorThing, caplog):
    r"""Check always_raises errors nicely when retrieved over HTTP.

    Note that `caplog` here is capturing the *server* log, the client-side
    code doesn't log, but does raise a `ClientPropertyError`\ .
    """
    with pytest.raises(ClientPropertyError, match="failed, as expected"):
        _ = client.always_raises
    assert caplog.record_tuples == [
        ("labthings_fastapi.things.thing", 40, "'always_raises' failed, as expected."),
    ]


def test_set_always_raises_server(client: ErrorThing, caplog):
    """Check always_raises errors nicely when set over HTTP."""
    with pytest.raises(ClientPropertyError, match="failed, as expected"):
        client.always_raises = 42
    assert caplog.record_tuples == [
        ("labthings_fastapi.things.thing", 40, "'always_raises' failed, as expected."),
    ]


def test_reset_always_raises_server(client: lt.ThingClient, caplog):
    """Check always_raises errors when reset over HTTP."""
    # Reset isn't yet exposed in ThingClient, so we do it manually.
    response = client.client.post("/thing/always_raises/reset")
    assert response.status_code == 500
    value = response.json()
    assert value["detail"] == "'always_raises' failed, as expected."
    assert value["title"] == "SpecificError"


def test_wrongly_typed_server(client: ErrorThing, caplog):
    """Check the error when we return a wrongly typed value."""
    with pytest.raises(
        ClientPropertyError,
        match="Error validating thing.wrongly_typed",
    ):
        _ = client.wrongly_typed
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    assert "Error validating thing.wrongly_typed" in caplog.records[0].getMessage()


def test_violates_constraint_server(client: ErrorThing, caplog):
    """Check we can retrieve a value that violates its constraint.

    Constraints are not yet validated on the return values of property
    getters.
    """
    with pytest.raises(
        ClientPropertyError,
        match="Error validating thing.violates_constraint",
    ):
        _ = client.violates_constraint
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    assert "validating thing.violates_constraint" in caplog.records[0].getMessage()
