"""Test the ThingServer.

While the server is covered by many of the other tests, it would
be helpful to have some more bottom-up unit testing in this file.
"""

import pytest
import labthings_fastapi as lt
from fastapi.testclient import TestClient
from starlette.routing import Route


def test_server_from_config_non_thing_error():
    """Test a typeerror is raised if something that's not a Thing is added."""
    with pytest.raises(TypeError, match="not a Thing"):
        lt.ThingServer.from_config(
            lt.ThingServerConfig(
                things={"thingone": lt.ThingConfig(cls="builtins:object")}
            )
        )


def test_server_thing_descriptions():
    """Check the server ThingDescriptions.

    Check the expected Action and Properties and their URLS are in the server
    thing_descriptions.
    """
    conf = {
        "things": {
            "thing1": "labthings_fastapi.example_things:MyThing",
            "thing2": {
                "class": "labthings_fastapi.example_things:MyThing",
                "kwargs": {},
            },
        }
    }

    thing_names = ["thing1", "thing2"]
    props = ["counter", "foo"]
    actions = [
        "action_with_only_kwargs",
        "action_without_arguments",
        "anaction",
        "increment_counter",
        "make_a_dict",
        "slowly_increase_counter",
    ]

    server = lt.ThingServer.from_config(conf)
    with TestClient(server.app) as client:
        response = client.get("/thing_descriptions/")
    response.raise_for_status()
    thing_descriptions = response.json()

    for thing_name in thing_names:
        thing_description = thing_descriptions[thing_name]
        for action_name in actions:
            action = thing_description["actions"][action_name]
            expected_href = thing_name + "/" + action_name
            assert action["forms"][0]["href"] == expected_href

        for prop_name in props:
            prop = thing_description["properties"][prop_name]
            expected_href = thing_name + "/" + prop_name
            assert prop["forms"][0]["href"] == expected_href


def test_api_prefix():
    """Check we can add a prefix to the URLs on a server."""

    class Example(lt.Thing):
        """An example Thing"""

    server = lt.ThingServer(things={"example": Example}, api_prefix="/api/v3")
    paths = [route.path for route in server.app.routes if isinstance(route, Route)]
    for expected_path in [
        "/api/v3/action_invocations",
        "/api/v3/action_invocations/{id}",
        "/api/v3/action_invocations/{id}/output",
        "/api/v3/action_invocations/{id}",
        "/api/v3/blob/{blob_id}",
        "/api/v3/thing_descriptions/",
        "/api/v3/example/",
    ]:
        assert expected_path in paths

    unprefixed_paths = {p for p in paths if not p.startswith("/api/v3/")}
    assert unprefixed_paths == {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
