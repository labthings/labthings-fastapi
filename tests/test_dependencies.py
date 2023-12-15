"""Tests for the dependency classes.

NB see test_thing_dependencies for tests of the dependency-injection mechanism
for actions.
"""

from fastapi import Depends, FastAPI, Request
from labthings_fastapi.dependencies.invocation import InvocationID
from labthings_fastapi.file_manager import FileManagerDep
from fastapi.testclient import TestClient
from module_with_deps import FancyIDDep


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

    class DepClass:
        def __init__(self, sub: Request):
            self.sub = sub

    @app.post("/dep")
    def endpoint(id: DepClass = Depends()) -> bool:
        return True

    with TestClient(app) as client:
        r = client.post("/dep")
        assert r.status_code == 200
        invocation = r.json()
        assert invocation is True


def test_file_manager():
    app = FastAPI()

    @app.post("/invoke_with_file")
    def invoke_with_file(
        file_manager: FileManagerDep,
    ) -> dict[str, str]:
        return {"directory": str(file_manager.directory)}

    with TestClient(app) as client:
        r = client.post("/invoke_with_file")
        assert r.status_code == 200
