"""Test the fallback server.

If the server is started from the command line, with ``--fallback`` specified,
we start a lightweight fallback server to show an error message. This test
verifies that it works as expected.
"""

from fastapi.testclient import TestClient
import labthings_fastapi as lt
from labthings_fastapi.server.fallback import app


def test_fallback_empty():
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        # test that something when wrong is shown
        assert "Something went wrong" in html
        assert "No logging info available" in html


def test_fallback_with_config():
    app.labthings_config = {"hello": "goodbye"}
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        assert "No logging info available" in html
        assert '"hello": "goodbye"' in html


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
    config_dict = {
        "things": {
            "thing1": "labthings_fastapi.example_things:MyThing",
            "thing2": {
                "class": "labthings_fastapi.example_things:MyThing",
                "kwargs": {},
            },
        }
    }
    config = lt.ThingServerConfig.model_validate(config_dict)
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
