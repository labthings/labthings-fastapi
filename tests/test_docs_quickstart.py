from subprocess import Popen, PIPE, STDOUT
import os
from pathlib import Path
import runpy
from test_server_cli import MonitoredProcess


def run_quickstart_counter():
    this_file = Path(__file__)
    repo = this_file.parents[1]
    quickstart = repo / "docs" / "source" / "quickstart" / "counter.py"
    runpy.run_path(quickstart)


def test_quickstart_counter():
    """Check we can create a server from the command line"""
    p = MonitoredProcess(target=run_quickstart_counter)
    p.run_monitored(terminate_outputs=["Application startup complete"])