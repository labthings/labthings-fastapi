"""Test the ThingServer.

Currently, this adds one trivial test for an error.

While the server is covered by many of the other tests, it would
be helpful to have some more bottom-up unit testing in this file.
"""

import pytest
from labthings_fastapi import server as ts


def test_server_from_config_non_thing_error():
    """Test a typeerror is raised if something that's not a Thing is added."""
    with pytest.raises(TypeError, match="not a Thing"):
        ts.server_from_config({"things": {"thingone": {"class": "builtins:object"}}})
