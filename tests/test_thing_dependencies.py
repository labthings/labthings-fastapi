"""
This tests Things that depend on other Things
"""

import inspect
from fastapi.testclient import TestClient
from fastapi import Request
import pytest
from labthings_fastapi.server import ThingServer
from temp_client import poll_task
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.dependencies.raw_thing import raw_thing_dependency
from labthings_fastapi.dependencies.thing import direct_thing_client_dependency
from labthings_fastapi.client.in_server import direct_thing_client_class
from labthings_fastapi.utilities.introspection import fastapi_dependency_params


class ThingOne(Thing):
    ACTION_ONE_RESULT = "Action one result!"

    @thing_action
    def action_one(self) -> str:
        """An action that takes no arguments"""
        return self.action_one_internal()

    def action_one_internal(self) -> str:
        return self.ACTION_ONE_RESULT


ThingOneDep = direct_thing_client_dependency(ThingOne, "/thing_one/")


class ThingTwo(Thing):
    @thing_action
    def action_two(self, thing_one: ThingOneDep) -> str:
        """An action that needs a ThingOne"""
        return thing_one.action_one()

    @thing_action
    def action_two_a(self, thing_one: ThingOneDep) -> str:
        """Another action that needs a ThingOne"""
        return thing_one.action_one()


ThingTwoDep = direct_thing_client_dependency(ThingTwo, "/thing_two/")


class ThingThree(Thing):
    @thing_action
    def action_three(self, thing_two: ThingTwoDep) -> str:
        """An action that needs a ThingTwo"""
        # Note that we don't have to supply the ThingOne dependency
        return thing_two.action_two()


def dependency_names(func: callable) -> list[str]:
    """Get the names of the dependencies of a function"""
    return [p.name for p in fastapi_dependency_params(func)]


def test_direct_thing_dependency():
    """Check that direct thing clients are distinct classes"""
    ThingOneClient = direct_thing_client_class(ThingOne, "/thing_one/")
    ThingTwoClient = direct_thing_client_class(ThingTwo, "/thing_two/")
    print(f"{ThingOneClient}: ThingOneClient{inspect.signature(ThingOneClient)}")
    for k in dir(ThingOneClient):
        if k.startswith("__"):
            continue
        print(f"{k}: {getattr(ThingOneClient, k)}")
    print(f"{ThingTwoClient}: ThingTwoClient{inspect.signature(ThingTwoClient)}")
    for k in dir(ThingTwoClient):
        if k.startswith("__"):
            continue
        print(f"{k}: {getattr(ThingTwoClient, k)}")
    assert ThingOneClient is not ThingTwoClient
    assert ThingOneClient.__init__ is not ThingTwoClient.__init__
    assert "thing_one" not in dependency_names(ThingOneClient)
    assert "thing_one" in dependency_names(ThingTwoClient)


def test_interthing_dependency():
    """Test that a Thing can depend on another Thing

    This uses the internal thing client mechanism.
    """
    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one")
    server.add_thing(ThingTwo(), "/thing_two")
    with TestClient(server.app) as client:
        r = client.post("/thing_two/action_two")
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert invocation["output"] == ThingOne.ACTION_ONE_RESULT


def test_interthing_dependency_with_dependencies():
    """Test that a Thing can depend on another Thing

    This uses the internal thing client mechanism, and requires
    dependency injection for the called action
    """
    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one")
    server.add_thing(ThingTwo(), "/thing_two")
    server.add_thing(ThingThree(), "/thing_three")
    with TestClient(server.app) as client:
        r = client.post("/thing_three/action_three")
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert invocation["output"] == ThingOne.ACTION_ONE_RESULT


def test_raw_interthing_dependency():
    """Test that a Thing can depend on another Thing

    This uses the internal thing client mechanism.
    """
    ThingOneDep = raw_thing_dependency(ThingOne)

    class ThingTwo(Thing):
        @thing_action
        def action_two(self, thing_one: ThingOneDep) -> str:
            """An action that needs a ThingOne"""
            return thing_one.action_one()

    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one")
    server.add_thing(ThingTwo(), "/thing_two")
    with TestClient(server.app) as client:
        r = client.post("/thing_two/action_two")
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        assert invocation["output"] == ThingOne.ACTION_ONE_RESULT


def test_conflicting_dependencies():
    """Dependencies are stored by argument name, and can't be duplicated.
    We check here that an error is raised if the same argument name is used
    for two different dependencies.

    This also checks that dependencies on the same class but different
    actions are recognised as "different".
    """
    ThingTwoDepNoActions = direct_thing_client_dependency(ThingTwo, "/thing_two/", [])

    class ThingFour(Thing):
        @thing_action
        def action_four(self, thing_two: ThingTwoDepNoActions) -> str:
            return str(thing_two)

        @thing_action
        def action_five(self, thing_two: ThingTwoDep) -> str:
            return thing_two.action_two()

    with pytest.raises(ValueError):
        direct_thing_client_dependency(ThingFour, "/thing_four/")


def check_request():
    """Check that the `Request` object has the same `app` as the server

    This is mostly just verifying that there's nothing funky in between the
    Starlette `Request` object and the FastAPI `app`."""
    server = ThingServer()

    @server.app.get("/check_request_app/")
    def check_request_app(request: Request) -> bool:
        return request.app is server.app

    with TestClient(server.app) as client:
        r = client.get("/check_request_app/")
        assert r.json() is True
