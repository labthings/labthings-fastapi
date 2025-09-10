"""Test the ThingServer.

Currently, this adds one trivial test for an error.

While the server is covered by many of the other tests, it would
be helpful to have some more bottom-up unit testing in this file.
"""

import pytest
from fastapi.testclient import TestClient
import labthings_fastapi as lt
from labthings_fastapi import server


def test_thing_with_blocking_portal_error(mocker):
    """Test that a thing with a _labthings_blocking_portal causes an error."""

    class Example(lt.Thing):
        def __init__(self):
            super().__init__()
            self._labthings_blocking_portal = mocker.Mock()

    server = lt.ThingServer()
    server.add_thing(Example(), "/example")
    with pytest.raises(RuntimeError):
        with TestClient(server.app) as client:
            pass


def test_server_from_config_non_thing_error():
    """Test a typeerror is raised if something that's not a Thing is added."""
    with pytest.raises(TypeError):
        server.server_from_config({"/thingone": {"class": "builtins:object"}})
