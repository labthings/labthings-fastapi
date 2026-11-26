"""Subclass `uvicorn.Server` so we can hook into the shutdown event."""

import socket
from collections.abc import Awaitable, Callable
from logging import getLogger

from uvicorn import Server

logger = getLogger(__name__)


class ServerWithShutdownHandler(Server):
    """A subclass of `uvicorn.Server` that provides a shutdown hook."""

    shutdown_callback: Callable[[], Awaitable[None]] | None = None

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        """Call the callback function before this method is called on the superclass.

        :param sockets: a list of sockets that are open.
        """
        try:
            if self.shutdown_callback is not None:
                logger.info("Awaiting shutdown callback.")
                await self.shutdown_callback()
        finally:
            # Make sure we shut down, even if there's an error.
            await super().shutdown(sockets=sockets)
