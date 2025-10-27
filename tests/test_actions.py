import uuid
from fastapi.testclient import TestClient
import pytest
import functools

from labthings_fastapi.thing_server_interface import create_thing_without_server
from .temp_client import poll_task, get_link
from labthings_fastapi.example_things import MyThing
import labthings_fastapi as lt


@pytest.fixture
def client():
    """Yield a client connected to a ThingServer"""
    server = lt.ThingServer({"thing": MyThing})
    with TestClient(server.app) as client:
        yield client


def action_partial(client: TestClient, url: str):
    def run(payload=None):
        r = client.post(url, json=payload)
        assert r.status_code in (200, 201)
        return poll_task(client, r.json())

    return run


def test_get_action_invocations(client):
    """Test that running "get" on an action returns a list of invocations."""
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


def test_counter(client):
    """Test that the increment_counter action increments the property."""
    before_value = client.get("/thing/counter").json()
    r = client.post("/thing/increment_counter")
    assert r.status_code in (200, 201)
    poll_task(client, r.json())
    after_value = client.get("/thing/counter").json()
    assert after_value == before_value + 1


def test_no_args(client):
    """Test None and {} are both accepted as input.

    Actions that take no arguments will accept either an empty
    dictionary or None as their input.

    Note that there is an assertion in `action_partial` so we
    do check that the action runs.
    """
    run = action_partial(client, "/thing/action_without_arguments")
    run({})  # an empty dict should be OK
    run(None)  # it should also be OK to call it with None
    # Calling with no payload is equivalent to None


def test_only_kwargs(client):
    """Test an action that only has **kwargs works as expected.

    It should be allowable to invoke such an action with no
    input (see test above) or with arbitrary keyword arguments.

    Note that there is an assertion in `action_partial` so we
    do check that the action runs.
    """
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


def test_action_output(client):
    """Test that an action's output may be retrieved directly.

    This tests the /action_invocation/{id}/output endpoint, including
    some error conditions (not found/output not available).
    """
    # Start an action and wait for it to complete
    r = client.post("/thing/make_a_dict", json={})
    r.raise_for_status()
    invocation = poll_task(client, r.json())
    assert invocation["status"] == "completed"
    assert invocation["output"] == {"key": "value"}
    # Retrieve the output directly and check it matches
    r = client.get(get_link(invocation, "output")["href"])
    assert r.json() == {"key": "value"}

    # Test an action that doesn't have an output
    r = client.post("/thing/action_without_arguments", json={})
    r.raise_for_status()
    invocation = poll_task(client, r.json())
    assert invocation["status"] == "completed"
    assert invocation["output"] is None

    # If the output is None, retrieving it directly should fail
    r = client.get(get_link(invocation, "output")["href"])
    assert r.status_code == 503

    # Repeat the last check, using a manually generated URL
    # (mostly to check the manually generated URL is valid,
    # so the next test can be trusted).
    r = client.get(f"/action_invocation/{invocation['id']}/output")
    assert r.status_code == 404

    # Test an output on a non-existent invocation
    r = client.get(f"/action_invocation/{uuid.uuid4()}/output")
    assert r.status_code == 404


def test_openapi(client):
    """Check the OpenAPI docs are generated OK"""
    r = client.get("/openapi.json")
    r.raise_for_status()


def example_decorator(func):
    """Decorate a function using functools.wraps."""

    @functools.wraps(func)
    def action_wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        return result

    return action_wrapper


def assert_input_models_equivalent(model_a, model_b):
    """Check two basemodels are equivalent."""
    keys = list(model_a.model_fields.keys())
    assert list(model_b.model_fields.keys()) == keys

    for k in keys:
        field_a = model_a.model_fields[k]
        field_b = model_b.model_fields[k]
        assert str(field_a.annotation) == str(field_b.annotation)
        assert field_a.default == field_b.default


def test_wrapped_action():
    """Check functools.wraps does not confuse schema generation"""

    class Example(lt.Thing):
        @lt.thing_action
        def action(
            self,
            portal: lt.deps.BlockingPortal,
            param1: int = 0,
            param2: str = "string",
        ) -> float | None:
            """An example action with type annotations."""
            return 0.5

        @lt.thing_action
        @example_decorator
        def decorated(
            self,
            portal: lt.deps.BlockingPortal,
            param1: int = 0,
            param2: str = "string",
        ) -> float | None:
            """An example decorated action with type annotations."""
            return 0.5

    assert_input_models_equivalent(
        Example.action.input_model, Example.decorated.input_model
    )
    assert Example.action.output_model == Example.decorated.output_model

    # Check we can make the thing and it has a valid TD
    example = create_thing_without_server(Example)
    example.validate_thing_description()
