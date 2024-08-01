from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import fastapi_endpoint
from pydantic import BaseModel


class PostBodyModel(BaseModel):
    a: int
    b: int


class TestThing(Thing):
    @fastapi_endpoint("get")
    def path_from_name(self) -> str:
        return "path_from_name"

    @fastapi_endpoint("get", path="path_from_path")
    def get_method(self) -> str:
        return "get_method"

    @fastapi_endpoint("post", path="path_from_path")
    def post_method(self, body: PostBodyModel) -> str:
        return f"post_method {body.a} {body.b}"


def test_endpoints():
    server = ThingServer()
    server.add_thing(TestThing(), "/thing")
    with TestClient(server.app) as client:
        r = client.get("/thing/path_from_name")
        r.raise_for_status()
        assert r.json() == "path_from_name"

        r = client.get("/thing/path_from_path")
        r.raise_for_status()
        assert r.json() == "get_method"

        r = client.post("/thing/path_from_path", json={"a": 1, "b": 2})
        r.raise_for_status()
        assert r.json() == "post_method 1 2"
