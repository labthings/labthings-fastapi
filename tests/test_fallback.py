"""Test the fallback server.

If the server is started from the command line, with ``--fallback`` specified,
we start a lightweight fallback server to show an error message. This test
verifies that it works as expected.
"""

import re

from fastapi.testclient import TestClient
import labthings_fastapi as lt
from labthings_fastapi.server.fallback import app

CONFIG_DICT = {
    "things": {
        "thing1": "labthings_fastapi.example_things:MyThing",
        "thing2": {
            "class": "labthings_fastapi.example_things:MyThing",
            "kwargs": {},
        },
    }
}


def test_fallback_empty():
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        # test that something when wrong is shown
        assert "Something went wrong" in html
        assert "No logging info available" in html


def test_fallback_with_config_dict():
    """Check that fallback server prints a config dictionary as JSON."""
    app.labthings_config = CONFIG_DICT
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        assert "No logging info available" in html
        assert '"thing1": "labthings_fastapi.example_things:MyThing"' in html
        assert '"class": "labthings_fastapi.example_things:MyThing"' in html


def test_fallback_with_config_obj():
    """Check that fallback server prints the config object as JSON."""
    config = lt.ThingServerConfig.model_validate(CONFIG_DICT)
    app.labthings_config = config
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        assert "No logging info available" in html
        assert "thing1" in html
        assert "thing2" in html
        cls_regex = re.compile(r'"cls": "labthings_fastapi\.example_things\.MyThing"')
        assert len(cls_regex.findall(html)) == 2


def test_fallback_with_error():
    app.labthings_error = RuntimeError("Custom error message")
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        assert "No logging info available" in html
        assert "RuntimeError" in html
        assert "Custom error message" in html


def test_fallback_with_server():
    config = lt.ThingServerConfig.model_validate(CONFIG_DICT)
    app.labthings_server = lt.ThingServer.from_config(config)
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        assert "No logging info available" in html
        assert "thing1" in html
        assert "thing2" in html


def test_fallback_with_log():
    app.log_history = "Fake log content"
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        assert "No logging info available" not in html
        assert "<p>Logging info</p>" in html
        assert "Fake log content" in html
