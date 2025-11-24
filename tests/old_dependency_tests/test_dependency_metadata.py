"""
This tests metadata retrieval, as used by e.g. the camera for EXIF info
"""

from typing import Any, Mapping
import warnings
from fastapi.testclient import TestClient
import pytest
from ..temp_client import poll_task
import labthings_fastapi as lt


pytestmark = pytest.mark.filterwarnings(
    "ignore:.*removed in v0.0.13.*:DeprecationWarning"
)


class ThingOne(lt.Thing):
    def __init__(self, thing_server_interface):
        super().__init__(thing_server_interface=thing_server_interface)
        self._a = 0

    @lt.property
    def a(self):
        return self._a

    @a.setter
    def a(self, value):
        self._a = value

    @property
    def thing_state(self):
        return {"a": self.a}


with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    ThingOneDep = lt.deps.direct_thing_client_dependency(ThingOne, "thing_one")


class ThingTwo(lt.Thing):
    A_VALUES = [1, 2, 3]

    @property
    def thing_state(self):
        return {"a": 1}

    @lt.action
    def count_and_watch(
        self, thing_one: ThingOneDep, get_metadata: lt.deps.GetThingStates
    ) -> Mapping[str, Mapping[str, Any]]:
        metadata = {}
        for a in self.A_VALUES:
            thing_one.a = a
            metadata[f"a_{a}"] = get_metadata()
        return metadata


@pytest.fixture
def client():
    """Yield a test client connected to a ThingServer."""
    server = lt.ThingServer(
        {
            "thing_one": ThingOne,
            "thing_two": ThingTwo,
        }
    )
    with TestClient(server.app) as client:
        yield client


def test_fresh_metadata(client):
    """Check that fresh metadata is retrieved by get_thing_states."""
    r = client.post("/thing_two/count_and_watch")
    invocation = poll_task(client, r.json())
    assert invocation["status"] == "completed"
    out = invocation["output"]
    for a in ThingTwo.A_VALUES:
        assert out[f"a_{a}"]["thing_one"]["a"] == a
        assert out[f"a_{a}"]["thing_two"]["a"] == 1
