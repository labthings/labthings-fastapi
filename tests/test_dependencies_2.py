"""MWE of a pydantic/FastAPI problem, kept for safety

Class-based dependencies in modules with `from __future__ import annotations`
fail if they have sub-dependencies, because the global namespace is not found by
pydantic. The work-around is to add a line to each class definition:
```
__globals__ = globals()
```
This bakes in the global namespace of the module, and allows FastAPI to correctly
traverse the dependency tree.

The tests in this module were written while I was figuring this out: they mostly
test things from FastAPI that obviously work, but I will leave them in here as
mitigation against something changing in the future.
"""

from typing import Annotated
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from module_with_deps import FancyIDDep, FancyID, ClassDependsOnFancyID
from labthings_fastapi.dependencies.invocation import InvocationID, invocation_id
from labthings_fastapi.file_manager import FileManager
from uuid import UUID


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
    def invoke_fancy(id: FancyID = Depends()) -> dict:
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
    def endpoint(id: DepClass = Depends()) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/dep")
        assert r.status_code == 200
        invocation = r.json()
        assert invocation is True


def test_class_dep_with_subdep():
    """Add an endpoint that uses a dependency class with sub-dependency"""
    app = FastAPI()

    class SubDepClass:
        pass

    class DepClass:
        def __init__(self, sub: Annotated[SubDepClass, Depends()]):
            self.sub = sub

    @app.post("/dep")
    def endpoint(id: DepClass = Depends()) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/dep")
        assert r.status_code == 200
        invocation = r.json()
        assert invocation is True


def test_invocation_id():
    """Add an endpoint that uses a dependency from another file"""
    app = FastAPI()

    @app.post("/endpoint")
    def invoke_fancy(id: Annotated[UUID, Depends(invocation_id)]) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/endpoint")
        assert r.status_code == 200


def test_invocation_id_alias():
    """Add an endpoint that uses a dependency from another file"""
    app = FastAPI()

    @app.post("/endpoint")
    def endpoint(id: InvocationID) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/endpoint")
        assert r.status_code == 200


def test_filemanager_dep():
    """Test out our FileManager class as a dependency"""
    app = FastAPI()

    @app.post("/endpoint")
    def endpoint(fm: Annotated[FileManager, Depends()]) -> str:
        return f"Saving to {fm.directory}"

    with TestClient(app) as client:
        r = client.post("/endpoint")
        assert r.status_code == 200
        assert r.json().startswith("Saving to ")
