from fastapi.testclient import TestClient
import pytest
from labthings_fastapi.thing_server import ThingServer
from temp_client import poll_task, get_link
import time
from typing import Optional, Annotated
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.descriptors import PropertyDescriptor
from pydantic import Field


class TestThing(Thing):
    @thing_action
    def anaction(
        self,
        repeats: Annotated[
            int, Field(description="The number of times to try the action")
        ],  # no default = required parameter
        undocumented: int,
        title: Annotated[
            str, Field(description="the title of the invocation")
        ] = "Untitled",
        attempts: Annotated[
            Optional[list[str]],
            Field(
                description="Names for each attempt - I suggest final, Final, FINAL."
            ),
        ] = None,
    ) -> dict[str, str]:
        """Quite a complicated action

        This action has lots of parameters and is designed to confuse my schema
        generator. I hope it doesn't!

        I might even use some Markdown here:

        * If this renders, it supports lists
        * With at east two items.
        """
        # We should be able to call actions as normal Python functions
        self.increment_counter()
        return {"end_result": "finished!!"}

    @thing_action
    def make_a_dict(
        self,
        extra_key: Optional[str] = None,
        extra_value: Optional[str] = None,
    ) -> dict[str, str]:
        """An action that returns a dict"""
        out = {"key": "value"}
        if extra_key is not None:
            out[extra_key] = extra_value
        return out

    @thing_action
    def increment_counter(self):
        """Increment the counter property

        This action doesn't do very much - all it does, in fact,
        is increment the counter (which may be read using the
        `counter` property).
        """
        self.counter += 1

    @thing_action
    def slowly_increase_counter(self):
        """Increment the counter slowly over a minute"""
        for i in range(60):
            time.sleep(1)
            self.increment_counter()

    counter = PropertyDescriptor(
        model=int, initial_value=0, readonly=True, description="A pointless counter"
    )

    foo = PropertyDescriptor(
        model=str,
        initial_value="Example",
        description="A pointless string for demo purposes.",
    )

    @thing_action
    def action_without_arguments(self) -> None:
        """An action that takes no arguments"""
        pass

    @thing_action
    def action_with_only_kwargs(self, **kwargs) -> None:
        """An action that takes **kwargs"""
        pass


thing = TestThing()
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
