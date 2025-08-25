from fastapi.testclient import TestClient
import pytest

from labthings_fastapi.exceptions import NotConnectedToServerError
from .temp_client import poll_task, get_link
from labthings_fastapi.example_things import MyThing
import labthings_fastapi as lt

thing = MyThing()
server = lt.ThingServer()
server.add_thing(thing, "/thing")


def action_partial(client: TestClient, url: str):
    def run(payload=None):
        r = client.post(url, json=payload)
        assert r.status_code in (200, 201)
        return poll_task(client, r.json())

    return run


def test_get_action_invocations():
    """Test that running "get" on an action returns a list of invocations."""
    with TestClient(server.app) as client:
        # When we start the action has no invocations
        invocations_before = client.get("/thing/increment_counter").json()
        assert invocations_before == []
        # Start the action
        r = client.post("/thing/increment_counter")
        assert r.status_code in (200, 201)
        # Now it is started, there is a list of 1 dictionary containing the
        # invocation information.
        invocations_after = client.get("/thing/increment_counter").json()
        assert len(invocations_after) == 1
        assert isinstance(invocations_after, list)
        assert isinstance(invocations_after[0], dict)
        assert "status" in invocations_after[0]
        assert "id" in invocations_after[0]
        assert "action" in invocations_after[0]
        assert "href" in invocations_after[0]
        assert "timeStarted" in invocations_after[0]
        # Let the task finish before ending the test
        poll_task(client, r.json())


def test_counter():
    with TestClient(server.app) as client:
        before_value = client.get("/thing/counter").json()
        r = client.post("/thing/increment_counter")
        assert r.status_code in (200, 201)
        poll_task(client, r.json())
        after_value = client.get("/thing/counter").json()
        assert after_value == before_value + 1


def test_no_args():
    with TestClient(server.app) as client:
        run = action_partial(client, "/thing/action_without_arguments")
        run({})  # an empty dict should be OK
        run(None)  # it should also be OK to call it with None
        # Calling with no payload is equivalent to None


def test_only_kwargs():
    with TestClient(server.app) as client:
        run = action_partial(client, "/thing/action_with_only_kwargs")
        run({})  # an empty dict should be OK
        run(None)  # it should also be OK to call it with None
        run({"foo": "bar"})  # it should be OK to call it with a payload


def test_varargs():
    """Test that we can't use *args in an action"""
    with pytest.raises(TypeError):

        @lt.thing_action
        def action_with_varargs(self, *args) -> None:
            """An action that takes *args"""
            pass


def test_action_output():
    with TestClient(server.app) as client:
        r = client.post("/thing/make_a_dict", json={})
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert invocation["output"] == {"key": "value"}
        r = client.get(get_link(invocation, "output")["href"])
        assert r.json() == {"key": "value"}


def test_openapi():
    """Check the OpenAPI docs are generated OK"""
    with TestClient(server.app) as client:
        r = client.get("/openapi.json")
        r.raise_for_status()


def test_affordance_and_fastapi_errors(mocker):
    """Check that we get a sensible error if the Thing has no path.

    The thing will not have a ``path`` property before it has been added
    to a server.
    """
    thing = MyThing()
    with pytest.raises(NotConnectedToServerError):
        MyThing.anaction.add_to_fastapi(mocker.Mock(), thing)
    with pytest.raises(NotConnectedToServerError):
        MyThing.anaction.action_affordance(thing, None)
