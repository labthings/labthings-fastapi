from labthings_fastapi.example_things import MyThing
from labthings_fastapi import ThingServer
from labthings_fastapi.testing import create_thing_without_server


def test_td_validates():
    """This will raise an exception if it doesn't validate OK"""
    thing = create_thing_without_server(MyThing)
    assert thing.validate_thing_description() is None


def test_add_thing():
    """Check that thing can be added to the server"""
    server = ThingServer({"thing": MyThing})
    assert isinstance(server.things["thing"], MyThing)


def test_thing_can_access_application_config():
    """Check that a thing can access its application config."""
    conf = {
        "things": {"thing1": MyThing, "thing2": MyThing},
        "application_config": {"foo": "bar", "mock": True},
    }

    server = ThingServer.from_config(conf)
    thing1 = server.things["thing1"]
    thing2 = server.things["thing2"]

    # Check both Things can access the application config
    thing1_config = thing1._thing_server_interface.application_config
    thing2_config = thing2._thing_server_interface.application_config
    assert thing1_config == {"foo": "bar", "mock": True}
    assert thing1_config == thing2_config
    # But that they are not the same dictionary, preventing mutations affecting
    # behaviour of another thing.
    assert thing1_config is not thing2_config
