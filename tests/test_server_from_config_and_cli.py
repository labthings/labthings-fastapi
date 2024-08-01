import json
import multiprocessing
import tempfile
import time
import traceback

from pytest import raises

from labthings_fastapi.server import server_from_config, ThingServer
from labthings_fastapi.server.cli import serve_from_cli


class ProcessPropagatingExceptions(multiprocessing.Process):
    """A process that remembers exceptons, and raises them on join()

    With thanks to:
    https://stackoverflow.com/questions/63758186
    """

    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self, *args, **kwargs)
        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

    def run(self):
        try:
            multiprocessing.Process.run(self)
            self._cconn.send(None)
        except Exception as e:
            tb = traceback.format_exc()
            self._cconn.send((e, tb))

    @property
    def exception(self):
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception

    def join(self):
        try:
            if self.exception:
                e, _tb = self.exception
                raise e
        finally:
            multiprocessing.Process.join(self)


CONFIG = {
    "things": {
        "thing1": "labthings_fastapi.example_things:MyThing",
        "thing2": {
            "class": "labthings_fastapi.example_things:MyThing",
            "kwargs": {},
        },
    }
}


def test_server_from_config():
    """Check we can create a server from a config object"""
    server = server_from_config(CONFIG)
    assert isinstance(server, ThingServer)


def check_serve_from_cli(args: list[str] = []):
    """Check we can create a server from the command line"""
    p = ProcessPropagatingExceptions(
        target=serve_from_cli, args=(args,)
    )
    p.start()
    time.sleep(1)
    p.terminate()
    p.join()


def test_serve_from_cli_with_config_json():
    """Check we can create a server from the command line, using JSON"""
    config_json = json.dumps(CONFIG)
    check_serve_from_cli(["-j", config_json])


def test_serve_from_cli_with_config_file():
    """Check we can create a server from the command line, using a file"""
    config_json = json.dumps(CONFIG)
    with tempfile.NamedTemporaryFile("w", delete=False) as temp:
        with open(temp.name, "w") as f:
            f.write(config_json)
            f.flush()
        check_serve_from_cli(["-c", temp.name])


def test_serve_with_no_config_without_multiprocessing():
    with raises(RuntimeError):
        serve_from_cli([], dry_run=True)


def test_serve_with_no_config():
    """Check an empty config fails, using multiprocessing.
    This is important, because if it passes it means our tests above
    are not actually testing anything.
    """
    with raises(RuntimeError):
        check_serve_from_cli([])
