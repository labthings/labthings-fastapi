"""Test the ThingServer.

While the server is covered by many of the other tests, it would
be helpful to have some more bottom-up unit testing in this file.
"""

import pytest
import labthings_fastapi as lt
from starlette.routing import Route

from labthings_fastapi.example_things import MyThing
from labthings_fastapi.server.config_model import ThingServerConfig


def test_server_from_config_non_thing_error():
    """Test a typeerror is raised if something that's not a Thing is added."""
    with pytest.raises(TypeError, match="not a Thing"):
        lt.ThingServer(
            lt.ThingServerConfig(
                things={"thingone": lt.ThingConfig(cls="builtins:object")}
            )
        )


def test_server_thing_descriptions():
    """Check the server `/thing_descriptions/` endpoint.

    Check the expected Action and Properties and their URLS are in the server
    thing_descriptions. This checks the endpoint that returns all of the
    Thing Descriptions in one big JSON object.
    """
    conf = {
        "things": {
            "thing1": "labthings_fastapi.example_things:MyThing",
            "thing2": {
                "class": "labthings_fastapi.example_things:MyThing",
                "kwargs": {},
            },
        },
        "api_prefix": "/api",
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

    server = lt.ThingServer(conf)
    with server.test_client() as client:
        response = client.get("/api/thing_descriptions/")
    response.raise_for_status()
    thing_descriptions = response.json()

    for thing_name in thing_names:
        thing_description = thing_descriptions[thing_name]

        expected_description = "An example Thing with a few affordances."
        assert thing_description["description"] == expected_description

        for action_name in actions:
            action = thing_description["actions"][action_name]
            expected_href = f"/api/{thing_name}/{action_name}"
            assert action["forms"][0]["href"] == expected_href

        for prop_name in props:
            prop = thing_description["properties"][prop_name]
            expected_href = f"/api/{thing_name}/{prop_name}"
            assert prop["forms"][0]["href"] == expected_href


@pytest.mark.parametrize("api_prefix", ["/api/v3", "/v1", "/custom/prefix"])
def test_api_prefix(api_prefix):
    """Check we can add a prefix to the URLs on a server."""

    class Example(lt.Thing):
        """An example Thing"""

    server = lt.ThingServer.from_things({"example": Example}, api_prefix=api_prefix)
    paths = [route.path for route in server.app.routes if isinstance(route, Route)]

    # Dynamically generate expected paths based on the parametrized prefix
    expected_paths = [
        f"{api_prefix}/action_invocations",
        f"{api_prefix}/action_invocations/{{id}}",
        f"{api_prefix}/action_invocations/{{id}}/output",
        f"{api_prefix}/blob/{{blob_id}}",
        f"{api_prefix}/thing_descriptions/",
        f"{api_prefix}/things/",
        f"{api_prefix}/example/",
    ]

    for expected_path in expected_paths:
        assert expected_path in paths

    prefix_with_slash = f"{api_prefix}/"
    unprefixed_paths = {p for p in paths if not p.startswith(prefix_with_slash)}

    assert unprefixed_paths == {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }


def test_things_endpoints():
    """Test that the two endpoints for listing Things work.

    This checks for consistency between `/things/` and `/thing_descriptions`
    (the former should map Thing names to URLs, while the latter should map
    Thing names to Thing Descriptions).

    This includes downloading the Thing Description from each URL and verifying
    it matches the object included in the `/thing_descriptions/` response.
    """
    server = lt.ThingServer.from_things(
        {
            "thing_a": MyThing,
            "thing_b": MyThing,
        }
    )
    with server.test_client() as client:
        # Check the thing_descriptions endpoint
        response = client.get("/thing_descriptions/")
        response.raise_for_status()
        tds = response.json()
        assert "thing_a" in tds
        assert "thing_b" in tds

        # Check the things endpoint. This should map names to URLs
        response = client.get("/things/")
        response.raise_for_status()
        things = response.json()
        assert "thing_a" in things
        assert "thing_b" in things

        # Fetch thing descriptions from the URL in `things`
        for name in things.keys():
            response = client.get(things[name])
            response.raise_for_status()
            td = response.json()
            assert td["title"] == "MyThing"
            assert tds[name] == td


@pytest.mark.parametrize(
    ("input", "validated"),
    [
        (None, False),
        (True, True),
        (False, False),
    ],
)
def test_debug_flag(input, validated):
    """Check that the debug flag can be retrieved."""
    kwargs = {}
    if input is not None:
        kwargs["debug"] = input
    server = lt.ThingServer.from_things({}, **kwargs)
    assert server.debug is validated
    with pytest.raises(AttributeError):
        server.debug = False


def test_settings_folder():
    """Check that the settings folder behaves correctly."""
    # Without setting a value, it should take the default value
    server = lt.ThingServer.from_things({})
    assert server.settings_folder == "./settings"
    server._config.settings_folder = None  # Deliberately induce error
    with pytest.raises(RuntimeError):
        # If the config object has None for the settings folder,
        # an error should be raised. This is set to a string in
        # __init__.
        _ = server.settings_folder

    # The settings folder should be settable from an argument or config
    server = lt.ThingServer.from_things({}, settings_folder="./mysettings")
    assert server.settings_folder == "./mysettings"

    # The settings folder should be settable from an argument or config
    server = lt.ThingServer(
        lt.ThingServerConfig(things={}, settings_folder="./mysettings")
    )
    assert server.settings_folder == "./mysettings"


def test_server_init():
    """Check the various different ways in which the server may be initialised."""
    config_dict = {
        "things": {
            "my_thing": MyThing,
        },
        "api_prefix": "/api/v3",
    }
    config_model = ThingServerConfig(**config_dict)

    def check_server(server: lt.ThingServer, debug: bool = False):
        """Make sure the server config is as expected."""
        assert len(server.things) == 1
        assert isinstance(server.things["my_thing"], MyThing)
        assert server.api_prefix == "/api/v3"
        assert server.debug == debug

    # The type hint doesn't match a dict, but it works anyway.
    check_server(lt.ThingServer(config_dict))
    # Supplying a model is the "right" way to do it
    check_server(lt.ThingServer(config_model))
    # The old usage should use `from_things`
    check_server(
        lt.ThingServer.from_things(config_dict["things"], api_prefix="/api/v3")
    )
    check_server(
        lt.ThingServer.from_things(config_model.thing_configs, api_prefix="/api/v3")
    )
    check_server(lt.ThingServer(config_model, debug=True), debug=True)
    # ThingServer.from_config is retired in favour of the constructor
    with pytest.warns(DeprecationWarning, match="redundant"):
        check_server(lt.ThingServer.from_config(config_model))
    # `things` can still be passed as kwargs, but it's deprecated
    with pytest.warns(DeprecationWarning, match="keyword arguments"):
        check_server(lt.ThingServer(**config_dict))
    # Supplying config and **kwargs is an error
    with pytest.raises(ValueError, match="no extra keyword arguments"):
        lt.ThingServer(config_model, settings_folder="./foo")
    # Invalid configuration raises a TypeError, with upgrade message
    with pytest.raises(TypeError, match="from_things"):
        lt.ThingServer(config_dict["things"])
