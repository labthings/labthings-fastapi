from fastapi.testclient import TestClient
import pytest
import httpx
from labthings_fastapi.server import ThingServer
from temp_client import poll_task
import time
from labthings_fastapi.thing import Thing
from labthings_fastapi.decorators import thing_action
from labthings_fastapi.descriptors import PropertyDescriptor


class TestThing(Thing):
    @thing_action(retention_time=0.01)
    def increment_counter(self):
        """Increment the counter"""
        self.counter += 1

    counter = PropertyDescriptor(
        model=int, initial_value=0, readonly=True, description="A pointless counter"
    )


thing = TestThing()
server = ThingServer()
server.add_thing(thing, "/thing")


def action_partial(client: TestClient, url: str):
    def run(payload=None):
        r = client.post(url, json=payload)
        assert r.status_code in (200, 201)
        return poll_task(client, r.json())

    return run


def test_expiry():
    with TestClient(server.app) as client:
        before_value = client.get("/thing/counter").json()
        r = client.post("/thing/increment_counter")
        invocation = poll_task(client, r.json())
        time.sleep(0.02)
        r2 = client.post("/thing/increment_counter")
        poll_task(client, r2.json())
        after_value = client.get("/thing/counter").json()
        assert after_value == before_value + 2
        invocation["status"] = "running"  # Force an extra poll
        with pytest.raises(httpx.HTTPStatusError):
            poll_task(client, invocation)
