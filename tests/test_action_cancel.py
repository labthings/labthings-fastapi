"""
This tests the log that is returned in an action invocation
"""

import uuid
from fastapi.testclient import TestClient
from temp_client import poll_task, task_href
import labthings_fastapi as lt
import time


class CancellableCountingThing(lt.Thing):
    counter = lt.ThingProperty[int](initial_value=0, observable=False)
    check = lt.ThingProperty[bool](
        initial_value=False,
        observable=False,
        description=(
            "This variable is used to check that the action can detect a cancel event "
            "and react by performing another task, in this case, setting this variable."
        ),
    )

    @lt.thing_action
    def count_slowly(self, cancel: lt.deps.CancelHook, n: int = 10):
        for i in range(n):
            try:
                cancel.sleep(0.1)
            except lt.exceptions.InvocationCancelledError as e:
                # Set check to true to show that cancel was called.
                self.check = True
                raise (e)
            self.counter += 1

    @lt.thing_action
    def count_slowly_but_ignore_cancel(self, cancel: lt.deps.CancelHook, n: int = 10):
        """
        Used to check that cancellation alter task behaviour
        """
        counting_increment = 1
        for i in range(n):
            try:
                cancel.sleep(0.1)
            except lt.exceptions.InvocationCancelledError:
                # Rather than cancel, this disobedient task just counts faster
                counting_increment = 3
            self.counter += counting_increment

    @lt.thing_action
    def count_and_only_cancel_if_asked_twice(
        self, cancel: lt.deps.CancelHook, n: int = 10
    ):
        """
        A task that changes behaviour on cancel, but if asked a second time will cancel
        """
        cancelled_once = False
        counting_increment = 1
        for i in range(n):
            try:
                cancel.sleep(0.1)
            except lt.exceptions.InvocationCancelledError as e:
                # If this is the second time, this is called actually cancel.
                if cancelled_once:
                    raise (e)
                # If not, remember that this cancel event happened.
                cancelled_once = True
                # Reset the CancelHook
                cancel.clear()
                # Count backwards instead!
                counting_increment = -1
            self.counter += counting_increment


def test_invocation_cancel():
    """
    Test that an invocation can be cancelled and the associated
    exception handled correctly.
    """
    server = lt.ThingServer()
    counting_thing = CancellableCountingThing()
    server.add_thing(counting_thing, "/counting_thing")
    with TestClient(server.app) as client:
        assert counting_thing.counter == 0
        assert not counting_thing.check
        response = client.post("/counting_thing/count_slowly", json={})
        response.raise_for_status()
        # Use `client.delete` to cancel the task!
        cancel_response = client.delete(task_href(response.json()))
        # Raise an exception is this isn't a 2xx response
        cancel_response.raise_for_status()
        invocation = poll_task(client, response.json())
        assert invocation["status"] == "cancelled"
        assert counting_thing.counter < 9
        # Check that error handling worked
        assert counting_thing.check


def test_invocation_that_refuses_to_cancel():
    """
    Test that an invocation can detect a cancel request but choose
    to modify behaviour.
    """
    server = lt.ThingServer()
    counting_thing = CancellableCountingThing()
    server.add_thing(counting_thing, "/counting_thing")
    with TestClient(server.app) as client:
        assert counting_thing.counter == 0
        response = client.post(
            "/counting_thing/count_slowly_but_ignore_cancel", json={"n": 5}
        )
        response.raise_for_status()
        # Use `client.delete` to try to cancel the task!
        cancel_response = client.delete(task_href(response.json()))
        # Raise an exception is this isn't a 2xx response
        cancel_response.raise_for_status()
        invocation = poll_task(client, response.json())
        # As the task ignored the cancel. It should return completed
        assert invocation["status"] == "completed"
        # Counter should be greater than 5 as it counts faster if cancelled!
        assert counting_thing.counter > 5


def test_invocation_that_needs_cancel_twice():
    """
    Test that an invocation can interpret cancel to change behaviour, but
    can really cancel if requested a second time
    """
    server = lt.ThingServer()
    counting_thing = CancellableCountingThing()
    server.add_thing(counting_thing, "/counting_thing")
    with TestClient(server.app) as client:
        # First cancel only once:
        assert counting_thing.counter == 0
        response = client.post(
            "/counting_thing/count_and_only_cancel_if_asked_twice", json={"n": 5}
        )
        response.raise_for_status()
        # Use `client.delete` to try to cancel the task!
        cancel_response = client.delete(task_href(response.json()))
        # Raise an exception is this isn't a 2xx response
        cancel_response.raise_for_status()
        invocation = poll_task(client, response.json())
        # As the task ignored the cancel. It should return completed
        assert invocation["status"] == "completed"
        # Counter should be less than 0 as it should started counting backwards
        # almost immediately.
        assert counting_thing.counter < 0

        # Next cancel twice.
        counting_thing.counter = 0
        assert counting_thing.counter == 0
        response = client.post(
            "/counting_thing/count_and_only_cancel_if_asked_twice", json={"n": 5}
        )
        response.raise_for_status()
        # Use `client.delete` to try to cancel the task!
        cancel_response = client.delete(task_href(response.json()))
        # Raise an exception is this isn't a 2xx response
        cancel_response.raise_for_status()
        # Cancel again
        cancel_response2 = client.delete(task_href(response.json()))
        # Raise an exception is this isn't a 2xx response
        cancel_response2.raise_for_status()
        invocation = poll_task(client, response.json())
        # As the task ignored the cancel. It should return completed
        assert invocation["status"] == "cancelled"
        # Counter should be less than 0 as it should started counting backwards
        # almost immediately.
        assert counting_thing.counter < 0


def test_late_invocation_cancel_responds_503():
    """
    Test that cancelling an invocation after it completes returns a 503 response.
    """
    server = lt.ThingServer()
    counting_thing = CancellableCountingThing()
    server.add_thing(counting_thing, "/counting_thing")
    with TestClient(server.app) as client:
        assert counting_thing.counter == 0
        assert not counting_thing.check
        response = client.post("/counting_thing/count_slowly", json={"n": 1})
        response.raise_for_status()
        # Sleep long enough that task completes.
        time.sleep(0.3)
        poll_task(client, response.json())
        # Use `client.delete` to cancel the task!
        cancel_response = client.delete(task_href(response.json()))
        # Check a 503 code is returned
        assert cancel_response.status_code == 503
        # Check counter reached it's target
        assert counting_thing.counter == 1
        # Check that error handling wasn't called
        assert not counting_thing.check


def test_cancel_unknown_task():
    """
    Test that cancelling an unknown invocation returns a 404 response
    """
    server = lt.ThingServer()
    counting_thing = CancellableCountingThing()
    server.add_thing(counting_thing, "/counting_thing")
    with TestClient(server.app) as client:
        cancel_response = client.delete(f"/invocations/{uuid.uuid4()}")
        assert cancel_response.status_code == 404
