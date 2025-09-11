from fastapi.testclient import TestClient
from pydantic import BaseModel
import labthings_fastapi as lt


class PostBodyModel(BaseModel):
    a: int
    b: int


class MyThing(lt.Thing):
    @lt.fastapi_endpoint("get")
    def path_from_name(self) -> str:
        return "path_from_name"

    @lt.fastapi_endpoint("get", path="path_from_path")
    def get_method(self) -> str:
        return "get_method"

    @lt.fastapi_endpoint("post", path="path_from_path")
    def post_method(self, body: PostBodyModel) -> str:
        return f"post_method {body.a} {body.b}"


def test_endpoints():
    """Check endpoints may be added to the app and work as expected."""
    server = lt.ThingServer()
    server.add_thing("thing", MyThing)
    thing = server.things["thing"]
    with TestClient(server.app) as client:
        # Check the function works when used directly
        assert thing.path_from_name() == "path_from_name"
        # Check it works identically over HTTP. The path is
        # generated from the name of the function.
        r = client.get("/thing/path_from_name")
        r.raise_for_status()
        assert r.json() == "path_from_name"

        # get_method has an explicit path - check it can be
        # used both directly and via that path.
        assert thing.get_method() == "get_method"
        r = client.get("/thing/path_from_path")
        r.raise_for_status()
        assert r.json() == "get_method"

        # post_method uses the same path, for a different
        # function
        assert thing.post_method(PostBodyModel(a=1, b=2)) == "post_method 1 2"
        r = client.post("/thing/path_from_path", json={"a": 1, "b": 2})
        r.raise_for_status()
        assert r.json() == "post_method 1 2"
