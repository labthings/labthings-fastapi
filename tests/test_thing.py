from labthings_fastapi.example_things import MyThing
from labthings_fastapi import ThingServer


def test_td_validates():
    """This will raise an exception if it doesn't validate OK"""
    thing = MyThing()
    thing.path = "/mything"  # can't generate a TD without a path
    assert thing.validate_thing_description() is None


def test_add_thing():
    """Check that thing can be added to the server"""
    server = ThingServer()
    server.add_thing("thing", MyThing)
    assert isinstance(server.things["thing"], MyThing)
