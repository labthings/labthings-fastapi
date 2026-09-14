"""Test computed properties in isolation."""

from typing import Literal

import pytest

import labthings_fastapi as lt
from labthings_fastapi.computed_properties import computed_property
from labthings_fastapi.exceptions import PropertyNotObservableError
from labthings_fastapi.testing import create_thing_without_server


class MyThing(lt.Thing):
    quantity: int = lt.property(default=0)
    quantity2: int = lt.property(default=0)
    selector: Literal["q1", "q2"] = lt.property(default="q1")

    @computed_property
    def double(self) -> int:
        return 2 * self.quantity

    @computed_property
    def selected(self) -> int:
        if self.selector == "q1":
            return self.quantity
        elif self.selector == "q2":
            return self.quantity2
        else:
            raise ValueError("invalid selector")

    @lt.property
    def unobservable(self) -> str:
        return "unobservable"

    @computed_property
    def broken(self) -> str:
        return self.unobservable


def test_dependencies():
    thing = create_thing_without_server(MyThing)

    thing.quantity = 1
    assert thing.double == 2
    assert MyThing.double._dependencies[thing] == {"quantity"}

    assert thing.selected == 1
    assert MyThing.selected._dependencies[thing] == {"selector", "quantity"}

    thing.selector = "q2"
    thing.quantity2 = 10
    assert thing.selected == 10
    assert MyThing.selected._dependencies[thing] == {"selector", "quantity2"}


def test_unobservable():
    """Check computed properties error if they depend on unobservable quantities."""
    thing = create_thing_without_server(MyThing)
    with pytest.raises(PropertyNotObservableError):
        _ = thing.broken
