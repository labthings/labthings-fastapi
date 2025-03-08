from pathlib import Path
from runpy import run_path
from test_server_cli import MonitoredProcess
from fastapi.testclient import TestClient
from labthings_fastapi.client import ThingClient


this_file = Path(__file__)
repo = this_file.parents[1]
docs = repo / "docs" / "source"


def run_quickstart_counter():
    # A server is started in the `__name__ == "__main__" block`
    run_path(docs / "quickstart" / "counter.py")


def test_quickstart_counter():
    """Check we can create a server from the command line"""
    p = MonitoredProcess(target=run_quickstart_counter)
    p.run_monitored(terminate_outputs=["Application startup complete"])


def test_dependency_example():
    globals = run_path(docs / "dependencies" / "example.py", run_name="not_main")
    with TestClient(globals["server"].app) as client:
        testthing = ThingClient.from_url("/testthing/", client=client)
        testthing.increment_counter()
