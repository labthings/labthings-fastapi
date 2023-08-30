"""
This tests Things that depend on other Things
"""
from fastapi.testclient import TestClient
from fastapi import Request
from labthings_fastapi.thing_server import ThingServer
from temp_client import poll_task
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.dependencies.raw_thing import raw_thing_dependency
from labthings_fastapi.dependencies.thing import direct_thing_client_dependency


class ThingOne(Thing):
    ACTION_ONE_RESULT = "Action one result!"
    @thing_action
    def action_one(self) -> str:
        """An action that takes no arguments"""
        return self.action_one_internal()
    
    def action_one_internal(self) -> str:
        return self.ACTION_ONE_RESULT
    

def test_interthing_dependency():
    """Test that a Thing can depend on another Thing
    
    This uses the internal thing client mechanism.
    """
    ThingOneClient = direct_thing_client_dependency(ThingOne, "/thing_one/")

    class ThingTwo(Thing):
        @thing_action
        def action_two(self, thing_one: ThingOneClient) -> str:
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

def test_raw_interthing_dependency():
    """Test that a Thing can depend on another Thing
    
    This uses the internal thing client mechanism.
    """
    ThingOneDep = raw_thing_dependency(ThingOne)
    print(f"{ThingOneDep} should be a type alias for {ThingOne}")

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
