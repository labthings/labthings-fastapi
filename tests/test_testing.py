"""Test the `testing` module."""

import pytest

import labthings_fastapi as lt
from labthings_fastapi import testing


class ThingA(lt.Thing):
    friend: "ThingB" = lt.thing_slot()


class ThingB(lt.Thing):
    friend: "ThingA" = lt.thing_slot()


@pytest.mark.parametrize("mock_slots", [True, False])
def test_manual_connect(mock_slots):
    """Make sure we can create and connect Things without a server."""
    a = testing.create_thing_without_server(ThingA, mock_all_slots=mock_slots)
    b = testing.create_thing_without_server(ThingB, mock_all_slots=mock_slots)

    testing.manually_connect_thing_slot(a, "friend", b)
    testing.manually_connect_thing_slot(b, "friend", a)

    assert a.friend is b
    assert b.friend is a
