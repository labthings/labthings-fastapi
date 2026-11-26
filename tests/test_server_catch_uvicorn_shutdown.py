"""Test the subclass that hooks in to `uvicorn.Server.shutdown`."""

from unittest.mock import call

import pytest
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
    """Check that we call the callback before the superclass function."""
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


async def test_serverwithshutdownhandler_shutdown_withcallback_err(mocker, caplog):
    """Check that an exception in the callback still runs the superclass function."""
    mocks = mocker.AsyncMock()
    mocker.patch("uvicorn.Server.shutdown", mocks.superclass_shutdown)
    app = FastAPI()
    server = ServerWithShutdownHandler(Config(app))

    async def fail():
        raise RuntimeError("Callback failed.")

    # If a handler is present, it should be called as well.
    server.shutdown_callback = mocks.callback
    mocks.callback.side_effect = fail
    with pytest.raises(RuntimeError, match="Callback failed."):
        await server.shutdown([])
    # Check the calls are in the correct order (callback first)
    # This makes sure the server shutdown routine ran as intended.
    mocks.assert_has_calls([call.callback(), call.superclass_shutdown(sockets=[])])


if __name__ == "__main__":
    # This block lets us test a real server with a broken callback.
    # It's a pain to do this in unit tests, and I think
    # `test_serverwithshutdownhandler_shutdown_withcallback_err` is
    # the right thing to run. However, it was important to check it
    # in situ at least once, and we may as well preserve that test.
    from fastapi import FastAPI
    from uvicorn import Config

    async def bad_shutdown():
        raise RuntimeError("Oh Dear :(")

    try:
        app = FastAPI()
        server = ServerWithShutdownHandler(Config(app, port=0))
        server.shutdown_callback = bad_shutdown
        server.run()
    except KeyboardInterrupt:
        pass
