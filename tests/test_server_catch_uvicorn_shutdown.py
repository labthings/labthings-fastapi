"""Test the subclass that hooks in to `uvicorn.Server.shutdown`."""

from unittest.mock import call

from fastapi import FastAPI
from uvicorn import Config

from labthings_fastapi.server._catch_uvicorn_shutdown import ServerWithShutdownHandler


async def test_serverwithshutdownhandler_shutdown_nocallback(mocker):
    """Check that shutdown is not broken if there's no callback."""
    superclass_shutdown = mocker.AsyncMock()
    mocker.patch("uvicorn.Server.shutdown", superclass_shutdown)
    app = FastAPI()
    server = ServerWithShutdownHandler(Config(app))

    # By default there's no handler present: we should see no error,
    # and Server.shutdown() should be called.
    await server.shutdown([])
    superclass_shutdown.assert_called_once_with(sockets=[])


async def test_serverwithshutdownhandler_shutdown_withcallback(mocker, caplog):
    """Check that we call the callback before the superclass callback function."""
    mocks = mocker.AsyncMock()
    mocker.patch("uvicorn.Server.shutdown", mocks.superclass_shutdown)
    app = FastAPI()
    server = ServerWithShutdownHandler(Config(app))

    # If a handler is present, it should be called as well.
    server.shutdown_callback = mocks.callback
    with caplog.at_level("INFO"):
        await server.shutdown([])
    # Check the calls are in the correct order (callback first)
    mocks.assert_has_calls([call.callback(), call.superclass_shutdown(sockets=[])])
    assert caplog.record_tuples == [
        (
            "labthings_fastapi.server._catch_uvicorn_shutdown",
            20,
            "Awaiting shutdown callback.",
        )
    ]
