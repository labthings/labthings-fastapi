"""MWE of a pydantic/FastAPI problem, kept for safety

Class-based dependencies in modules with `from __future__ import annotations`
fail if they have sub-dependencies, because the global namespace is not found by
pydantic. The work-around was to add a line to each class definition:
```
__globals__ = globals()
```
This bakes in the global namespace of the module, and allows FastAPI to correctly
traverse the dependency tree.

This is related to https://github.com/fastapi/fastapi/issues/4557 and may have
been fixed upstream in FastAPI.

The tests in this module were written while I was figuring this out: they mostly
test things from FastAPI that obviously work, but I will leave them in here as
mitigation against something changing in the future.
"""

from dataclasses import dataclass
from typing import Annotated
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest
from .module_with_deps import FancyIDDep, FancyID, ClassDependsOnFancyID
import labthings_fastapi as lt


pytestmark = pytest.mark.filterwarnings(
    "ignore:.*removed in v0.1.0.*:DeprecationWarning"
)


def test_dep_from_module():
    """Add an endpoint that uses a dependency from another file"""
    app = FastAPI()

    @app.post("/invoke_fancy")
    def invoke_fancy(id: Annotated[FancyID, Depends()]) -> dict:
        return {"id": "me"}

    with TestClient(app) as client:
        r = client.post("/invoke_fancy")
        assert r.status_code == 200
        invocation = r.json()
        assert isinstance(invocation["id"], str)


def test_dep_from_module_with_subdep():
    """Add an endpoint that uses a dependency from another file"""
    app = FastAPI()

    @app.post("/endpoint")
    def endpoint(id: Annotated[ClassDependsOnFancyID, Depends()]) -> bool:
        # Verify that the dependency is supplied, including its sub-dependency
        assert id.sub.id == 1234
        return True

    with TestClient(app) as client:
        r = client.post("/endpoint")
        assert r.status_code == 200


def test_fancy_id_aliased():
    """Add an endpoint that uses a dependency from another file"""
    app = FastAPI()

    @app.post("/invoke_fancy")
    def invoke_fancy(id: FancyIDDep) -> dict:
        return {"id": "me"}

    with TestClient(app) as client:
        r = client.post("/invoke_fancy")
        assert r.status_code == 200
        invocation = r.json()
        assert isinstance(invocation["id"], str)


def test_fancy_id_default():
    """Add an endpoint that uses a dependency from another file"""
    app = FastAPI()

    @app.post("/invoke_fancy")
    def invoke_fancy(id: Annotated[FancyID, Depends()]) -> dict:
        return {"id": "me"}

    with TestClient(app) as client:
        r = client.post("/invoke_fancy")
        assert r.status_code == 200
        invocation = r.json()
        assert isinstance(invocation["id"], str)


def test_class_dep():
    """Add an endpoint that uses a dependency class"""
    app = FastAPI()

    class DepClass:
        pass

    @app.post("/dep")
    def endpoint(id: Annotated[DepClass, Depends()]) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/dep")
        assert r.status_code == 200
        invocation = r.json()
        assert invocation is True


def test_class_dep_with_subdep():
    """Add an endpoint that uses a dependency class with sub-dependency.

    We do this twice, using a regular class and also a dataclass.
    """
    app = FastAPI()

    class SubDepClass:
        pass

    class DepClass:  # noqa B903
        """A regular class that has sub-dependencies via __init__.

        Note that this could be a dataclass, but we want to check both
        dataclasses and normal classes."""

        def __init__(self, sub: Annotated[SubDepClass, Depends()]):
            self.sub = sub

    @app.post("/dep")
    def endpoint(id: Annotated[DepClass, Depends()]) -> bool:
        assert isinstance(id.sub, SubDepClass)
        return True

    @dataclass
    class DepDataclass:
        sub: Annotated[SubDepClass, Depends()]

    @app.post("/dep2")
    def endpoint2(dep: Annotated[DepDataclass, Depends()]):
        assert isinstance(dep.sub, SubDepClass)
        return True

    with TestClient(app) as client:
        for url in ["/dep", "/dep2"]:
            r = client.post(url)
            assert r.status_code == 200
            invocation = r.json()
            assert invocation is True


def test_invocation_id():
    """Add an endpoint that uses a dependency imported from another file"""
    app = FastAPI()

    @app.post("/endpoint")
    def invoke_fancy(id: lt.deps.InvocationID) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/endpoint")
        assert r.status_code == 200


def test_invocation_id_alias():
    """Add an endpoint that uses a dependency alias from another file"""
    app = FastAPI()

    @app.post("/endpoint")
    def endpoint(id: lt.deps.InvocationID) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/endpoint")
        assert r.status_code == 200
