"""Test the `testing` module."""

from collections.abc import Mapping

import pytest

import labthings_fastapi as lt
from labthings_fastapi import testing


class ThingA(lt.Thing):
    """A Thing subclass that connects to ThingB and ThingC."""

    friend: "ThingB" = lt.thing_slot()
    friends: "Mapping[str, ThingC]" = lt.thing_slot()


class ThingB(lt.Thing):
    """A Thing subclass that connects to a ThingA,"""

    friend: "ThingA" = lt.thing_slot()


class ThingC(lt.Thing):
    """A dummy Thing subclass."""


@pytest.mark.parametrize("mock_slots", [True, False])
def test_manual_connect(mock_slots, mocker):
    """Make sure we can create and connect Things without a server."""
    a = testing.create_thing_without_server(ThingA, mock_all_slots=mock_slots)
    b = testing.create_thing_without_server(ThingB, mock_all_slots=mock_slots)
    c = testing.create_thing_without_server(ThingC, mock_all_slots=mock_slots)

    testing.manually_connect_thing_slot(a, "friend", b)
    testing.manually_connect_thing_slot(a, "friends", [c])
    testing.manually_connect_thing_slot(b, "friend", a)

    assert a.friend is b
    assert len(a.friends) == 1
    assert a.friends["thingc"] is c
    assert b.friend is a

    mc1 = mocker.Mock(spec=ThingC)
    mc1.name = "mock_c_1"
    mc2 = mocker.Mock(spec=ThingC)
    mc2.name = "mock_c_2"

    testing.manually_connect_thing_slot(a, "friends", [mc1, mc2])
    assert a.friends["mock_c_1"] is mc1
    assert a.friends["mock_c_2"] is mc2

    with pytest.raises(TypeError):
        testing.manually_connect_thing_slot(a, "friend", mocker.Mock())

    with pytest.raises(KeyError, match="are not uniquely named"):
        testing.manually_connect_thing_slot(a, "friend", [mc1, mc1])
