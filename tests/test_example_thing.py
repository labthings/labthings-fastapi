from labthings_fastapi.example_things import (
    MyThing,
    ThingWithBrokenAffordances,
    ThingThatCantInstantiate,
    ThingThatCantStart,
)
import pytest


class DummyBlockingPortal:
    """A dummy blocking portal for testing

    This is a blocking portal that doesn't actually do anything.
    In the future, we should improve LabThings so this is not required.
    """

    def start_task_soon(self, func, *args, **kwargs):
        pass


def test_mything():
    thing = MyThing()
    thing._labthings_blocking_portal = DummyBlockingPortal()
    assert isinstance(thing, MyThing)
    assert thing.counter == 0
    ret = thing.anaction(3, 1, title="MyTitle", attempts=["a", "b", "c"])
    assert ret == {"end_result": "finished!!"}
    ret = thing.make_a_dict("key2", "value2")
    assert ret == {"key": "value", "key2": "value2"}
    before = thing.counter
    thing.increment_counter()
    assert thing.counter == before + 1
    thing.slowly_increase_counter(3, 0)
    assert thing.counter == before + 4
    assert thing.foo == "Example"
    thing.foo = "New Value"
    assert thing.foo == "New Value"
    thing.action_without_arguments()
    thing.action_with_only_kwargs(foo="bar")


def test_thing_with_broken_affordances():
    thing = ThingWithBrokenAffordances()
    assert isinstance(thing, ThingWithBrokenAffordances)
    with pytest.raises(RuntimeError):
        thing.broken_action()
    with pytest.raises(RuntimeError):
        thing.broken_property()


def test_thing_that_cant_instantiate():
    with pytest.raises(Exception):
        ThingThatCantInstantiate()


def test_thing_that_cant_start():
    thing = ThingThatCantStart()
    assert isinstance(thing, ThingThatCantStart)
    with pytest.raises(Exception):
        with thing:
            pass
