from fastapi.testclient import TestClient
import pytest
from labthings_fastapi.server import ThingServer
from temp_client import poll_task, get_link
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.example_things import MyThing

thing = MyThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def action_partial(client: TestClient, url: str):
    def run(payload=None):
        r = client.post(url, json=payload)
        assert r.status_code in (200, 201)
        return poll_task(client, r.json())

    return run


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

        @thing_action
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
