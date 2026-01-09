"""Test the fallback server.

If the server is started from the command line, with ``--fallback`` specified,
we start a lightweight fallback server to show an error message. This test
verifies that it works as expected.
"""

import re

import pytest
import uvicorn

from fastapi.testclient import TestClient
import labthings_fastapi as lt
from labthings_fastapi.server.fallback import app
from labthings_fastapi.example_things import ThingThatCantStart

CONFIG_DICT = {
    "things": {
        "thing1": "labthings_fastapi.example_things:MyThing",
        "thing2": {
            "class": "labthings_fastapi.example_things:MyThing",
            "kwargs": {},
        },
    }
}


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset the fallback app state before each fallback test."""
    app.labthings_config = None
    app.labthings_server = None
    app.labthings_error = None
    app.log_history = None


def test_fallback_redirect():
    """Test that the redirect works."""
    with TestClient(app) as client:
        response = client.get("/")
        # No history as no redirect
        assert len(response.history) == 0
        html = response.text
        # test that something when wrong is shown
        assert "Something went wrong" in html

        # Now try another url
        response = client.get("/foo/bar")
        # redirected so there is a history item showing a 307 Temporary Redirect code.
        assert len(response.history) == 1
        assert response.history[0].status_code == 307

        # Redirects to error page.
        html = response.text
        # test that something when wrong is shown
        assert "Something went wrong" in html


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


def test_actual_server_fallback():
    """Test that the the server configures its startup failure correctly.

    This may want to become an integration test in the fullness of time. Though
    the integration test may want to actually let the cli really serve up the
    fallback.
    """
    # ThingThatCantStart has an error in __enter__
    server = lt.ThingServer({"bad_thing": ThingThatCantStart})

    # Starting the server is a SystemExit
    with pytest.raises(SystemExit, match="3") as excinfo:
        uvicorn.run(server.app, port=5000)
    server_error = excinfo.value
    assert server.startup_failure is not None
    assert server.startup_failure["thing"] == "bad_thing"
    thing_error = server.startup_failure["exception"]
    assert isinstance(thing_error, RuntimeError)

    app.labthings_server = server
    app.labthings_error = server_error
    with TestClient(app) as client:
        response = client.get("/")
        html = response.text
        assert "Something went wrong" in html
        # Shouldn't be displaying the meaningless SystemExit
        assert "SystemExit" not in html

        # The message from when the Thing errored should be displayed
        assert str(thing_error) in html
        # With the traceback
        assert 'labthings_fastapi/example_things/__init__.py", line' in html
        assert f'RuntimeError("{thing_error}")' in html
