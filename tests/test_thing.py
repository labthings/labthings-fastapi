from labthings_fastapi.example_things import MyThing


def test_td_validates():
    """This will raise an exception if it doesn't validate OK"""
    thing = MyThing()
    assert thing.validate_thing_description() is None
