"""
This tests the log that is returned in an action invocation
"""
from fastapi.testclient import TestClient
from labthings_fastapi.thing_server import ThingServer
from temp_client import poll_task, task_href
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.descriptors import PropertyDescriptor
from labthings_fastapi.dependencies.invocation import CancelHook


class ThingOne(Thing):
    counter = PropertyDescriptor(int, 0)

    @thing_action
    def count_slowly(self, cancel: CancelHook):
        for i in range(10):
            cancel.sleep(0.1)
            self.counter += 1


def test_invocation_logging():
    server = ThingServer()
    thing_one = ThingOne()
    server.add_thing(thing_one, "/thing_one")
    with TestClient(server.app) as client:
        r = client.post("/thing_one/count_slowly")
        r.raise_for_status()
        dr = client.delete(task_href(r.json()))
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "cancelled"
    assert thing_one.counter < 9
