"""Test the URLFor class and associated supporting code."""

import pytest
from pydantic import BaseModel
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
    with pytest.raises(TypeError):
        _ = ModelWithURL(url="https://example.com")
    with pytest.raises(TypeError):
        _ = ModelWithURL(url="endpoint_name")
    with pytest.raises(TypeError):
        _ = ModelWithURL(url=None)


def test_middleware():
    """Check the middleware function works as expected."""
    app = FastAPI()
    app.middleware("http")(url_for_middleware)

    class Model(BaseModel):
        url: str

    @app.get("/test-endpoint/{item_id}/", name="test-endpoint")
    async def test_endpoint(item_id: int) -> URLFor:
        return URLFor("test-endpoint", item_id=item_id)

    @app.get("/sync-endpoint/{item_id}/", name="sync-endpoint")
    async def sync_endpoint(item_id: int) -> URLFor:
        return URLFor("sync-endpoint", item_id=item_id)

    @app.get("/model-endpoint/{item_id}/", name="model-endpoint")
    async def model_endpoint(item_id: int) -> URLFor:
        return URLFor("model-endpoint", item_id=item_id)

    with TestClient(app) as client:
        response = client.get("/test-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == "http://testserver/test-endpoint/42/"

        response = client.get("/sync-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == "http://testserver/sync-endpoint/42/"

        response = client.get("/model-endpoint/42/")
        assert response.status_code == 200
        assert response.json() == "http://testserver/model-endpoint/42/"
