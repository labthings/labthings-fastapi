from pathlib import Path
from runpy import run_path
import pytest
from .test_server_cli import MonitoredProcess


this_file = Path(__file__)
repo = this_file.parents[1]
docs = repo / "docs" / "source"


def run_quickstart_counter():
    # A server is started in the `__name__ == "__main__" block`
    # Running from a WindowsPath confuses the documentation code
    # in `base_descriptor.get_class_attribute_docstrings` hence
    # the cast to a `str`
    run_path(str(docs / "quickstart" / "counter.py"))


@pytest.mark.slow
def test_quickstart_counter():
    """Check we can create a server from the command line"""
    p = MonitoredProcess(target=run_quickstart_counter)
    p.run_monitored(terminate_outputs=["Application startup complete"])
