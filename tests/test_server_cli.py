import json
import multiprocessing
import sys
import tempfile

from pytest import raises

from labthings_fastapi.server import server_from_config, ThingServer
from labthings_fastapi.server.cli import serve_from_cli


def monitored_target(target, conn, *args, **kwargs):
    """Monitor stdout and exceptions from a function"""
    # The lines below copy stdout messages to a pipe
    # which allows us to monitor STDOUT and STDERR
    for output, name in [(sys.stdout, "stdout"), (sys.stderr, "stderr")]:

        def write_wrapper(message):
            conn.send((name, message))

        output.write = write_wrapper

    try:
        ret = target(*args, **kwargs)
        conn.send(("success", ret))
    except Exception as e:
        conn.send(("exception", e))
    except SystemExit as e:
        conn.send(("exit", e))


class MonitoredProcess(multiprocessing.Process):
    """A process that monitors stdout and propagates exceptions to `join()`

    With thanks to:
    https://stackoverflow.com/questions/63758186
    """

    def __init__(self, target=None, **kwargs):
        self._pconn, self._cconn = multiprocessing.Pipe()
        args = (target, self._cconn) + kwargs.pop("args", ())
        multiprocessing.Process.__init__(
            self, target=monitored_target, args=args, **kwargs
        )

    def run_monitored(self, terminate_outputs=[], timeout=10):
        """Run the process, monitoring stdout and exceptions"""
        self.start()
        try:
            while self._pconn.poll(timeout):
                event, m = self._pconn.recv()
                if event == "success":
                    return m
                elif event in ("exception", "exit"):
                    raise m
                elif event in ("stdout", "stderr"):
                    print(f"{event.upper()}: {m}")
                    if any(output in m for output in terminate_outputs):
                        self.terminate()
                        break
                else:
                    raise RuntimeError(f"Unknown event: {event}, {m!r}")
            else:
                raise TimeoutError("Timed out waiting for process output")
        finally:
            self.join()


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
    p = MonitoredProcess(target=serve_from_cli, args=(args,))
    p.run_monitored(terminate_outputs=["Application startup complete"])


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


def test_invalid_thing_and_fallback():
    """Check it fails for invalid things, and test the fallback option"""
    config_json = json.dumps(
        {
            "things": {
                "broken": "labthings_fastapi.example_things:MissingThing",
            }
        }
    )
    with raises(ImportError):
        check_serve_from_cli(["-j", config_json])
    ## the line below should start a dummy server with an error page -
    ## it terminates happily once the server starts.
    check_serve_from_cli(["-j", config_json, "--fallback"])


def test_invalid_config():
    """Check it fails for invalid config"""
    with raises(FileNotFoundError):
        check_serve_from_cli(["-c", "non_existent_file.json"])


def test_thing_that_cant_start():
    """Check it fails for a thing that can't start"""
    config_json = json.dumps(
        {
            "things": {
                "broken": "labthings_fastapi.example_things:ThingThatCantStart",
            }
        }
    )
    with raises(SystemExit):
        check_serve_from_cli(["-j", config_json])


if __name__ == "__main__":
    test_serve_from_cli_with_config_json()
