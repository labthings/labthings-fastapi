"""Test the URLFor class and associated supporting code."""

import threading
import pytest
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticSerializationError
from fastapi import FastAPI
from starlette.testclient import TestClient

from labthings_fastapi.middleware import url_for
from labthings_fastapi.middleware.url_for import URLFor, url_for_middleware
from labthings_fastapi.testing import use_dummy_url_for
from labthings_fastapi.exceptions import NoUrlForContextError


class ModelWithURL(BaseModel):
    """A model containing a URLFor field."""

    url: URLFor


def test_url_for():
    """Check that the `url_for` function uses the context var as expected."""
    with pytest.raises(NoUrlForContextError):
        url_for.url_for("my_endpoint", id=123)
    with use_dummy_url_for():
        assert url_for.url_for("my_endpoint", id=123) == "urlfor://my_endpoint/?id=123"


def test_string_conversion(mocker):
    """Test that URLFor can be converted to a string."""
    url_for_spy = mocker.spy(url_for, "url_for")
    u = URLFor("my_endpoint", id=123)
    with pytest.raises(NoUrlForContextError):
        _ = str(u)
    with use_dummy_url_for():
        assert str(u) == "urlfor://my_endpoint/?id=123"
    assert url_for_spy.call_count == 2


def test_serialisation(mocker):
    """Test that URLFor is serialised by calling str() on it."""
    u = URLFor("my_endpoint", id=123)
    m = ModelWithURL(url=u)

    # Check that serialisation fails without a url_for context
    # and that it tries to call `url_for`
    with pytest.raises(NoUrlForContextError) as excinfo:
        _ = m.model_dump()
    assert "url_for" in [frame.name for frame in excinfo.traceback]
    with pytest.raises(PydanticSerializationError, match="NoUrlForContextError"):
        _ = m.model_dump_json()
    with use_dummy_url_for():
        assert m.model_dump()["url"] == "urlfor://my_endpoint/?id=123"


def test_validation():
    """Test that URLFor validation works as expected."""
    # URLFor is a custom type, so the initialiser works normally
    u = URLFor("my_endpoint", id=123)

    # Initialising with an instance should leave it unchanged
    m = ModelWithURL(url=u)
    assert m.url is u

    # Trying to initialise with anything else should raise an error
    msg = "URLFor instances may not be created from strings"
    with pytest.raises(ValidationError, match=msg):
        _ = ModelWithURL(url="https://example.com")
    with pytest.raises(ValidationError):
        _ = ModelWithURL(url="endpoint_name")
    with pytest.raises(ValidationError):
        _ = ModelWithURL(url=None)


def test_middleware():
    """Check the middleware function works as expected."""
    app = FastAPI()
    app.middleware("http")(url_for_middleware)

    class Model(BaseModel):
        url: URLFor

    @app.get("/test-endpoint/{item_id}/", name="test-endpoint")
    async def test_endpoint(item_id: int) -> URLFor:
        """An async endpoint that returns a URLFor instance."""
        return URLFor("test-endpoint", item_id=item_id)

    @app.get("/sync-endpoint/{item_id}/")
    def sync_endpoint(item_id: int) -> URLFor:
        """A sync endpoint that returns a URLFor instance."""
        return URLFor("test-endpoint", item_id=item_id)

    @app.get("/model-endpoint/{item_id}/")
    async def model_endpoint(item_id: int) -> Model:
        """An async endpoint that returns a model containing a URLFor."""
        return Model(url=URLFor("test-endpoint", item_id=item_id))

    @app.get("/direct-async-endpoint/{item_id}/")
    async def direct_async_endpoint(item_id: int) -> str:
        """An async endpoint that calls `url_for` directly."""
        return str(url_for.url_for("test-endpoint", item_id=item_id))

    @app.get("/direct_sync-endpoint/{item_id}/")
    def direct_sync_endpoint(item_id: int) -> str:
        """A sync endpoint that calls `url_for` directly."""
        return str(url_for.url_for("test-endpoint", item_id=item_id))

    def assert_url_for_fails(item_id: int):
        with pytest.raises(NoUrlForContextError):
            _ = url_for.url_for("test-endpoint", item_id=item_id)

    def append_from_thread(item_id: int, output: list) -> None:
        output.append(URLFor("test-endpoint", item_id=item_id))

    @app.get("/assert_fails_in_thread/{item_id}/")
    async def assert_fails_in_thread(item_id: int) -> bool:
        t = threading.Thread(target=assert_url_for_fails, args=(item_id,))
        t.start()
        t.join()
        return True

    @app.get("/return_from_thread/{item_id}/")
    async def return_from_thread(item_id: int) -> URLFor:
        output = []
        append_from_thread(item_id, output)
        return output[0]

    URL = "http://testserver/test-endpoint/42/"

    with TestClient(app) as client:
        response = client.get("/test-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == URL

        response = client.get("/sync-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == URL

        response = client.get("/model-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == {"url": URL}

        response = client.get("/direct-async-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == URL

        response = client.get("/direct_sync-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == URL

        response = client.get("/assert_fails_in_thread/42/")
        assert response.status_code == 200
        assert response.json() is True

        response = client.get("/return_from_thread/42/")
        assert response.status_code == 200
        assert response.json() == URL
