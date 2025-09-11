"""Test the ThingServer.

Currently, this adds one trivial test for an error.

While the server is covered by many of the other tests, it would
be helpful to have some more bottom-up unit testing in this file.
"""

import pytest
from fastapi.testclient import TestClient
import labthings_fastapi as lt
from labthings_fastapi import server as ts


def test_thing_with_blocking_portal_error(mocker):
    """Test that a thing with a _labthings_blocking_portal causes an error.

    The blocking portal is added when the server starts. If one is there already,
    this is an error and the server should fail to start.

    As this ends up in an async context manager, the exception will be wrapped
    in an ExceptionGroup, hence the slightly complicated code to test the exception.

    This is not an error condition that we expect to happen often. Handling
    it more elegantly would result in enough additional code that the burden of
    maintaining and testing that code outweighs the benefit of a more elegant
    error message.
    """

    class Example(lt.Thing):
        def __init__(self):
            super().__init__()
            self._labthings_blocking_portal = mocker.Mock()

    server = lt.ThingServer()
    server.add_thing(Example(), "/example")
    with pytest.RaisesGroup(pytest.RaisesExc(RuntimeError, match="blocking portal")):
        with TestClient(server.app):
            pass


def test_server_from_config_non_thing_error():
    """Test a typeerror is raised if something that's not a Thing is added."""
    with pytest.raises(TypeError, match="not a Thing"):
        ts.server_from_config({"things": {"/thingone": {"class": "builtins:object"}}})
