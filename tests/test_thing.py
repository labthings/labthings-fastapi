from labthings_fastapi.example_things import MyThing
from labthings_fastapi import ThingServer
from labthings_fastapi.thing_server_interface import create_thing_without_server


def test_td_validates():
    """This will raise an exception if it doesn't validate OK"""
    thing = create_thing_without_server(MyThing)
    assert thing.validate_thing_description() is None


def test_add_thing():
    """Check that thing can be added to the server"""
    server = ThingServer({"thing": MyThing})
    assert isinstance(server.things["thing"], MyThing)
