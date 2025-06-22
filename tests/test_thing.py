import pytest
from labthings_fastapi.example_things import MyThing
from labthings_fastapi.server import ThingServer


def test_td_validates():
    """This will raise an exception if it doesn't validate OK"""
    thing = MyThing()
    assert thing.validate_thing_description() is None


def test_add_thing():
    """Check that thing can be added to the server"""
    thing = MyThing()
    server = ThingServer()
    server.add_thing(thing, "/thing")


def test_add_naughty_thing():
    """Check that a thing trying to access server resources
    using .. is not allowed"""
    thing = MyThing()
    server = ThingServer()
    with pytest.raises(ValueError):
        server.add_thing(thing, "/../../../../bin")
