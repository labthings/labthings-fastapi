"""
This tests the log that is returned in an action invocation
"""

import uuid
from fastapi.testclient import TestClient
from temp_client import poll_task, task_href
import labthings_fastapi as lt


class ThingOne(lt.Thing):
    counter = lt.ThingProperty(int, 0, observable=False)

    @lt.thing_action
    def count_slowly(self, cancel: lt.CancelHook, n: int = 10):
        for i in range(n):
            cancel.sleep(0.1)
            self.counter += 1


def test_invocation_cancel():
    server = lt.ThingServer()
    thing_one = ThingOne()
    server.add_thing(thing_one, "/thing_one")
    with TestClient(server.app) as client:
        r = client.post("/thing_one/count_slowly", json={})
        r.raise_for_status()
        dr = client.delete(task_href(r.json()))
        dr.raise_for_status()
        invocation = poll_task(client, r.json())
        assert invocation["status"] == "cancelled"
        assert thing_one.counter < 9

        # Try again, but cancel too late - should get a 503.
        thing_one.counter = 0
        r = client.post("/thing_one/count_slowly", json={"n": 0})
        r.raise_for_status()
        invocation = poll_task(client, r.json())
        dr = client.delete(task_href(r.json()))
        assert dr.status_code == 503

        dr = client.delete(f"/invocations/{uuid.uuid4()}")
        assert dr.status_code == 404
