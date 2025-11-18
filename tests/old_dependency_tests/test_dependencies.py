"""Tests for the dependency classes.

NB see test_thing_dependencies for tests of the dependency-injection mechanism
for actions.
"""

from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, FastAPI, Request
from labthings_fastapi.deps import InvocationID
from fastapi.testclient import TestClient
import pytest
from .module_with_deps import FancyIDDep


pytestmark = pytest.mark.filterwarnings(
    "ignore:.*removed in v0.0.13.*:DeprecationWarning"
)


def test_invocation_id():
    """Test our InvocationID dependency doesn't cause an error"""
    app = FastAPI()

    @app.post("/invoke")
    def invoke(id: InvocationID) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/invoke")
        assert r.status_code == 200


def test_fancy_id():
    """Test a stub dependency from another file, using a type alias"""
    # TODO: can probably delete this, it's tested by test_invocation_id
    app = FastAPI()

    @app.post("/invoke_fancy")
    def invoke_fancy(id: FancyIDDep) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/invoke_fancy")
        assert r.status_code == 200


def test_dependency_needing_request():
    """Test a dependency that requires Request object"""
    app = FastAPI()

    @dataclass
    class DepClass:
        r"""A class that has a dependency in its __init__.

        This is a dataclass, so __init__ is generated automatically and
        will have an argument `sub` with type `Request`\ .
        """

        sub: Request

    @app.post("/dep")
    def endpoint(id: Annotated[DepClass, Depends()]) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/dep")
        assert r.status_code == 200
        invocation = r.json()
        assert invocation is True
