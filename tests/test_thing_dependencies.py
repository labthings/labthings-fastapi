"""
This tests Things that depend on other Things
"""
from fastapi.testclient import TestClient
from fastapi import Depends, Request
import pytest
from labthings_fastapi.client.in_server import direct_thing_client
from labthings_fastapi.thing_server import ThingServer
from temp_client import poll_task, get_link
import time
from typing import Optional, Annotated
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action


def test_interthing_dependency():
    """Test that a Thing can depend on another Thing
    
    This uses the internal thing client mechanism.
    """
    class ThingOne(Thing):
        ACTION_ONE_RESULT = "Action one result!"
        @thing_action
        def action_one(self) -> str:
            """An action that takes no arguments"""
            return self.ACTION_ONE_RESULT
    ThingOneClient = direct_thing_client(ThingOne, "/thing_one/")

    class ThingTwo(Thing):
        @thing_action
        def action_two(self, thing_one: Annotated[ThingOneClient, Depends()]) -> str:
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
