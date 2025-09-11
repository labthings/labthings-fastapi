r"""Interface between `.Thing` subclasses and the `.ThingServer`\ ."""

from __future__ import annotations
import os
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Awaitable, TypeVar
from weakref import ref, ReferenceType

from .exceptions import ServerNotRunningError

if TYPE_CHECKING:
    from .server import ThingServer
    from .thing import Thing


class ThingServerMissingError(RuntimeError):
    """The error raised when a ThingServer is no longer available.

    This error indicates that a ThingServerInterface is still in use
    even though its underlying ThingServer has been deleted. This is
    unlikely to happen and usually indicates that the server has
    been created in an odd way.
    """


class ThingServerInterface:
    r"""An interface for Things to interact with their server.

    This is added to every `.Thing` during ``__init__`` and is available
    as ``self._thing_server_interface``\ .
    """

    def __init__(self, server: ThingServer, name: str) -> None:
        """Initialise a ThingServerInterface.

        The ThingServerInterface sits between a Thing and its ThingServer,
        with the intention of providing a useful set of functions, without
        exposing too much of the server to the Thing.

        One reason for using this intermediary class is to make it easier
        to mock the server during testing: only functions provided here
        need be mocked, not the whole functionality of the server.

        :param server: the `.ThingServer` instance we're connected to.
            This will be retained as a weak reference.
        :param name: the name of the `.Thing` instance this interface
            is provided for.
        """
        self._name: str = name
        self._server: ReferenceType[ThingServer] = ref(server)

    def _get_server(self) -> ThingServer:
        """Return a live reference to the ThingServer.

        This will evaluate the weak reference to the ThingServer, and will
        raise an exception if the server has been garbage collected.

        The server is, in practice, not going to be finalized before the
        Things, so this should not be a problem.

        :returns: the ThingServer.

        :raises ThingServerMissingError: if the `ThingServer` is no longer
            available.
        """
        server = self._server()
        if server is None:
            raise ThingServerMissingError()
        return server

    def start_async_task_soon(self, async_function: Awaitable, *args: Any) -> None:
        """Run an asynchronous task in the server's event loop.

        This function wraps `anyio.from_thread.BlockingPortal.start_task_soon` to
        provide a way of calling asynchronous code from threaded code. It will
        call the provided async function in the server's event loop, without any
        guarantee of exactly when it will happen. This means we will return
        immediately, and the return value from ``async_function`` will not be
        available.

        :param async_function: the asynchronous function to call.
        :param *args: positional arguments to be provided to the function.
        """
        portal = self._get_server().blocking_portal
        if portal is None:
            raise ServerNotRunningError("Can't run async code without an event loop.")
        portal.start_task_soon(async_function, *args)

    @property
    def settings_folder(self) -> str:
        """The path to a folder where persistent files may be saved."""
        server = self._get_server()
        return os.path.join(server.settings_folder, self.name)

    @property
    def settings_file_path(self) -> str:
        """The path where settings should be loaded and saved as JSON."""
        return os.path.join(self.settings_folder, "settings.json")

    @property
    def name(self) -> str:
        """The name of the Thing attached to this interface."""
        return self._name

    @property
    def path(self) -> str:
        """The path, relative to the server's base URL, of the Thing.

        A ThingServerInterface is specific to one Thing, so this path points
        to the base URL of the Thing, i.e. the Thing Description's endpoint.
        """
        return f"/{self.name}/"


class MockThingServerInterface(ThingServerInterface):
    """A mock class that simulates a ThingServerInterface without the server."""

    def __init__(self, name: str) -> None:
        """Initialise a ThingServerInterface.

        :param name: The name of the Thing we're providing an interface to.
        """
        # We deliberately don't call super().__init__(), as it won't work without
        # a server.
        self._name: str = name
        self._settings_tempdir: TemporaryDirectory | None = None

    def start_async_task_soon(self, async_function: Awaitable, *args: Any) -> None:
        """Do nothing, as there's no event loop to use.

        :param async_function: the asynchronous function to call.
        :param *args: positional arguments to be provided to the function.
        """
        pass

    @property
    def settings_folder(self) -> str:
        """The path to a folder where persistent files may be saved."""
        if not self._settings_tempdir:
            self._settings_tempdir = TemporaryDirectory()
        return self._settings_tempdir.name


ThingSubclass = TypeVar("ThingSubclass", bound="Thing")


def create_thing_without_server(
    cls: type[ThingSubclass], *args: Any, **kwargs: Any
) -> ThingSubclass:
    r"""Create a `.Thing` and supply a mock ThingServerInterface.

    This function is intended for use in testing, where it will enable a `.Thing`
    to be created without a server, by supplying a `.MockThingServerInterface`
    instead of a real `.ThingServerInterface`\ .

    The name of the Thing will be taken from the class name, lowercased.

    :param cls: The `.Thing` subclass to instantiate.
    :param *args: positional arguments to ``__init__``.
    :param **kwargs: keyword arguments to ``__init__``.

    :returns: an instance of ``cls`` with a `.MockThingServerInterface`
        so that it will function without a server.
    """
    name = cls.__name__.lower()
    return cls(
        *args, **kwargs, thing_server_interface=MockThingServerInterface(name=name)
    )
