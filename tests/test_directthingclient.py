"""Test the DirectThingClient class.

This module tests inter-Thing interactions. It does not yet test exhaustively,
and has been added primarily to fix #165.
"""

from fastapi.testclient import TestClient
import pytest
import labthings_fastapi as lt
from lt.deps import DirectThingClient, direct_thing_client_class
from .temp_client import poll_task


class Counter(lt.Thing):
    ACTION_ONE_RESULT = "Action one result!"

    @lt.thing_action
    def increment(self) -> str:
        """An action that takes no arguments"""
        return self.increment_internal()

    def increment_internal(self) -> str:
        """An action that increments the counter."""
        self.count += self.step
        return self.ACTION_ONE_RESULT

    step: int = lt.property(default=1)
    count: int = lt.property(default=0, readonly=True)


@pytest.fixture
def counter_client(mocker) -> DirectThingClient:
    r"""Instantiate a Counter and wrap it in a DirectThingClient.

    In order to make this work without a server, ``DirectThingClient`` is
    subclassed, and ``__init__`` is overridden.
    This could be done with ``mocker`` but it would be more verbose and
    less clear.

    :param mocker: the mocker test fixture from ``pytest-mock``\ .
    :returns: a ``DirectThingClient`` subclass wrapping a ``Counter``\ .
    """
    counter = Counter()
    counter._labthings_blocking_portal = mocker.Mock(["start_task_soon"])

    CounterClient = direct_thing_client_class(Counter, "/counter")

    class StandaloneCounterClient(CounterClient):
        def __init__(self, wrapped):
            self._dependencies = {}
            self._request = mocker.Mock()
            self._wrapped_thing = wrapped

    return StandaloneCounterClient(counter)


CounterDep = lt.deps.direct_thing_client_dependency(Counter, "/counter/")
RawCounterDep = lt.deps.raw_thing_dependency(Counter)


class Controller(lt.Thing):
    """Controller is used to test a real DirectThingClient in a server.

    This is used by ``test_directthingclient_in_server`` to verify the
    client works as expected when created normally, rather than by mocking
    the server.
    """

    @lt.thing_action
    def count_in_twos(self, counter: CounterDep) -> str:
        """An action that needs a Counter and uses its affordances.

        This only uses methods that are part of the HTTP API, so all
        of these commands should work.
        """
        counter.step = 2
        assert counter.count == 0
        counter.increment()
        assert counter.count == 2
        return "success"

    @lt.thing_action
    def count_internal(self, counter: CounterDep) -> str:
        """An action that tries to access local-only attributes.

        This previously used `pytest.raises` but that caused the test
        to hang, most likely because this will run in a background thread.
        """
        try:
            counter.increment_internal()
            raise AssertionError("Expected error was not raised!")
        except AttributeError:
            # pytest.raises seems to hang.
            pass
        try:
            counter.count = 4
            raise AssertionError("Expected error was not raised!")
        except AttributeError:
            # pytest.raises seems to hang.
            pass
        return "success"

    @lt.thing_action
    def count_raw(self, counter: RawCounterDep) -> str:
        """Increment the counter using a method that is not an Action."""
        counter.count = 0
        counter.step = -1
        counter.increment_internal()
        assert counter.count == -1
        return "success"


def test_readwrite_property(counter_client):
    """Test a read/write property works as expected."""
    counter_client.step = 2
    assert counter_client.step == 2


def test_readonly_property(counter_client):
    """Test a read/write property works as expected."""
    assert counter_client.count == 0
    with pytest.raises(AttributeError):
        counter_client.count = 10


def test_action(counter_client):
    """Test we can run an action."""
    assert counter_client.count == 0
    counter_client.increment()
    assert counter_client.count == 1


def test_method(counter_client):
    """Methods that are not decorated as actions should be missing."""
    with pytest.raises(AttributeError):
        counter_client.increment_internal()
    # Just to double-check the line above isn't a typo...
    counter_client._wrapped_thing.increment_internal()


@pytest.mark.parametrize("action", ["count_in_twos", "count_internal", "count_raw"])
def test_directthingclient_in_server(action):
    """Test that a Thing can depend on another Thing

    This uses the internal thing client mechanism.
    """
    server = lt.ThingServer()
    server.add_thing(Counter(), "/counter")
    server.add_thing(Controller(), "/controller")
    with TestClient(server.app) as client:
        r = client.post(f"/controller/{action}")
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert invocation["output"] == "success"
