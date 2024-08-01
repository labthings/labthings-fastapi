"""
This tests metadata retrieval, as used by e.g. the camera for EXIF info
"""

from typing import Any, Mapping
from fastapi.testclient import TestClient
from labthings_fastapi.server import ThingServer
from temp_client import poll_task
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action, thing_property
from labthings_fastapi.dependencies.thing import direct_thing_client_dependency
from labthings_fastapi.dependencies.metadata import GetThingStates


class ThingOne(Thing):
    def __init__(self):
        Thing.__init__(self)
        self._a = 0

    @thing_property
    def a(self):
        return self._a

    @a.setter
    def a(self, value):
        self._a = value

    @property
    def thing_state(self):
        return {"a": self.a}


ThingOneDep = direct_thing_client_dependency(ThingOne, "/thing_one/")


class ThingTwo(Thing):
    A_VALUES = [1, 2, 3]

    @property
    def thing_state(self):
        return {"a": 1}

    @thing_action
    def count_and_watch(
        self, thing_one: ThingOneDep, get_metadata: GetThingStates
    ) -> Mapping[str, Mapping[str, Any]]:
        metadata = {}
        for a in self.A_VALUES:
            thing_one.a = a
            metadata[f"a_{a}"] = get_metadata()
        return metadata


def test_fresh_metadata():
    server = ThingServer()
    server.add_thing(ThingOne(), "/thing_one/")
    server.add_thing(ThingTwo(), "/thing_two/")
    with TestClient(server.app) as client:
        r = client.post("/thing_two/count_and_watch")
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "completed"
        out = invocation["output"]
        for a in ThingTwo.A_VALUES:
            assert out[f"a_{a}"]["/thing_one/"]["a"] == a
            assert out[f"a_{a}"]["/thing_two/"]["a"] == 1
