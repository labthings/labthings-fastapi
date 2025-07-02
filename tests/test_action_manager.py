from fastapi.testclient import TestClient
import pytest
import httpx
from temp_client import poll_task
import time
import labthings_fastapi as lt
from labthings_fastapi.actions import ACTION_INVOCATIONS_PATH


class TestThing(lt.Thing):
    @lt.thing_action(retention_time=0.01)
    def increment_counter(self):
        """Increment the counter"""
        self.counter += 1

    counter = lt.ThingProperty[int](
        model=int, initial_value=0, readonly=True, description="A pointless counter"
    )


thing = TestThing()
server = lt.ThingServer()
server.add_thing(thing, "/thing")


def test_action_expires():
    """Check the action is removed from the server

    We've set the retention period to be very short, so the action
    should not be retrievable after some time has elapsed.

    This test checks that actions do indeed get removed.

    Note that the code that expires actions runs whenever a new
    action is started. That's why we need to invoke the action twice:
    the second invocation runs the code that deletes the first one.
    This behaviour might change in the future, making the second run
    unnecessary.
    """
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
        # When the second action runs, the first one should expire
        # so polling it again should give a 404.
        with pytest.raises(httpx.HTTPStatusError):
            poll_task(client, invocation)


def test_actions_list():
    """Check that the /action_invocations/ path works.

    The /action_invocations/ path should return a list of invocation
    objects (a representation of each action that's been run recently).

    It's implemented in `ActionManager.list_all_invocations`.
    """
    with TestClient(server.app) as client:
        r = client.post("/thing/increment_counter")
        invocation = poll_task(client, r.json())
        r2 = client.get(ACTION_INVOCATIONS_PATH)
        r2.raise_for_status()
        invocations = r2.json()
        assert invocations == [invocation]
