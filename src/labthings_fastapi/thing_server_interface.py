r"""Interface between `.Thing` subclasses and the `.ThingServer`\ ."""

from __future__ import annotations
from concurrent.futures import Future
import os
from tempfile import TemporaryDirectory
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Mapping,
    ParamSpec,
    TypeVar,
    Iterable,
)
from weakref import ref, ReferenceType
from unittest.mock import Mock

from .exceptions import ServerNotRunningError
from .utilities import class_attributes
from .thing_slots import ThingSlot

if TYPE_CHECKING:
    from .server import ThingServer
    from .thing import Thing


Params = ParamSpec("Params")
ReturnType = TypeVar("ReturnType")


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

    def start_async_task_soon(
        self, async_function: Callable[Params, Awaitable[ReturnType]], *args: Any
    ) -> Future[ReturnType]:
        r"""Run an asynchronous task in the server's event loop.

        This function wraps `anyio.from_thread.BlockingPortal.start_task_soon` to
        provide a way of calling asynchronous code from threaded code. It will
        call the provided async function in the server's event loop, without any
        guarantee of exactly when it will happen. This means we will return
        immediately, and the return value of this function will be a
        `concurrent.futures.Future` object that may resolve to the async function's
        return value.

        :param async_function: the asynchronous function to call.
        :param \*args: positional arguments to be provided to the function.

        :returns: an `asyncio.Future` object wrapping the return value.

        :raises ServerNotRunningError: if the server is not running
            (i.e. there is no event loop).
        """
        portal = self._get_server().blocking_portal
        if portal is None:
            raise ServerNotRunningError("Can't run async code without an event loop.")
        return portal.start_task_soon(async_function, *args)

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
        return self._get_server().path_for_thing(self.name)

    def get_thing_states(self) -> Mapping[str, Any]:
        """Retrieve metadata from all Things on the server.

        This function will retrieve the `.Thing.thing_state` property from
        each `.Thing` on the server, and return it as a dictionary.
        It is intended to make it easy to add metadata to the results
        of actions, for example to embed in an image.

        :return: a dictionary of metadata, with the `.Thing` names as keys.
        """
        return {k: v.thing_state for k, v in self._get_server().things.items()}


class MockThingServerInterface(ThingServerInterface):
    r"""A mock class that simulates a ThingServerInterface without the server.

    This allows a `.Thing` to be instantiated but not connected to a server.
    The methods normally provided by the server are mocked, specifically:

    * The `name` is set by an argument to `__init__`\ .
    * `start_async_task_soon` silently does nothing, i.e. the async function
      will not be run.
    * The settings folder will either be specified when the class is initialised,
      or a temporary folder will be created.
    * `get_thing_states` will return an empty dictionary.
    """

    def __init__(self, name: str, settings_folder: str | None = None) -> None:
        """Initialise a ThingServerInterface.

        :param name: The name of the Thing we're providing an interface to.
        :param settings_folder: The location where we should save settings.
            By default, this is a temporary directory.
        """
        # We deliberately don't call super().__init__(), as it won't work without
        # a server.
        self._name: str = name
        self._settings_tempdir: TemporaryDirectory | None = None
        self._settings_folder = settings_folder
        self._mocks: list[Mock] = []

    def start_async_task_soon(
        self, async_function: Callable[Params, Awaitable[ReturnType]], *args: Any
    ) -> Future[ReturnType]:
        r"""Do nothing, as there's no event loop to use.

        This returns a `concurrent.futures.Future` object that is already cancelled,
        in order to avoid accidental hangs in test code that attempts to wait for
        the future object to resolve. Cancelling it may cause errors if you need
        the return value.

        If you need the async code to run, it's best to add the `.Thing` to a
        `lt.ThingServer` instead. Using a test client will start an event loop
        in a background thread, and allow you to use a real `.ThingServerInterface`
        without the overhead of actually starting an HTTP server.

        :param async_function: the asynchronous function to call.
        :param \*args: positional arguments to be provided to the function.

        :returns: a `concurrent.futures.Future` object that has been cancelled.
        """
        f: Future[ReturnType] = Future()
        f.cancel()
        return f

    @property
    def settings_folder(self) -> str:
        """The path to a folder where persistent files may be saved.

        This will create a temporary folder the first time it is called,
        and return the same folder on subsequent calls.

        :returns: the path to a temporary folder.
        """
        if self._settings_folder:
            return self._settings_folder
        if not self._settings_tempdir:
            self._settings_tempdir = TemporaryDirectory()
        return self._settings_tempdir.name

    @property
    def path(self) -> str:
        """The path, relative to the server's base URL, of the Thing.

        A ThingServerInterface is specific to one Thing, so this path points
        to the base URL of the Thing, i.e. the Thing Description's endpoint.
        """
        return f"/{self.name}/"

    def get_thing_states(self) -> Mapping[str, Any]:
        """Return an empty dictionary to mock the metadata dictionary.

        :returns: an empty dictionary.
        """
        return {}


ThingSubclass = TypeVar("ThingSubclass", bound="Thing")


def create_thing_without_server(
    cls: type[ThingSubclass],
    *args: Any,
    settings_folder: str | None = None,
    mock_all_slots: bool = False,
    **kwargs: Any,
) -> ThingSubclass:
    r"""Create a `.Thing` and supply a mock ThingServerInterface.

    This function is intended for use in testing, where it will enable a `.Thing`
    to be created without a server, by supplying a `.MockThingServerInterface`
    instead of a real `.ThingServerInterface`\ .

    The name of the Thing will be taken from the class name, lowercased.

    :param cls: The `.Thing` subclass to instantiate.
    :param \*args: positional arguments to ``__init__``.
    :param settings_folder: The path to the settings folder. A temporary folder
        is used by default.
    :param mock_all_slots: Set to True to create a `unittest.mock.Mock` object
        connected to each thing slot. It follows the default of the specified
        to the slot. So if an optional slot has a default of `None`, no mock
        will be provided.
    :param \**kwargs: keyword arguments to ``__init__``.

    :returns: an instance of ``cls`` with a `.MockThingServerInterface`
        so that it will function without a server.

    :raises ValueError: if a keyword argument called 'thing_server_interface'
        is supplied, as this would conflict with the mock interface.
    """
    name = cls.__name__.lower()
    if "thing_server_interface" in kwargs:
        msg = "You may not supply a keyword argument called 'thing_server_interface'."
        raise ValueError(msg)

    msi = MockThingServerInterface(name=name, settings_folder=settings_folder)
    # Note: we must ignore misc typing errors above because mypy flags an error
    # that `thing_server_interface` is multiply specified.
    # This is a conflict with *args, if we had only **kwargs it would not flag
    # any error.
    # Given that args and kwargs are dynamically typed anyway, this does not
    # lose us much.
    thing = cls(*args, **kwargs, thing_server_interface=msi)  # type: ignore[misc]
    if mock_all_slots:
        _mock_slots(thing)
    return thing


def _mock_slots(thing: Thing) -> None:
    """Mock the slots of a thing created by create_thing_without_server.

    :param thing: The thing to mock the slots of
    """
    for attr_name, attr in class_attributes(thing):
        if isinstance(attr, ThingSlot):
            # Simply use the class of the first type that can be used.
            mock_class = attr.thing_type[0]

            # The names of the mocks we need to create to make a mapping of mock
            # things for the slot to connect to.
            mock_names = []
            if attr.default is ...:
                # if default use the name of the slot with mock
                mock_names.append(f"mock-{attr_name}")
            elif isinstance(attr.default, str):
                mock_names.append(attr.default)
            elif isinstance(attr.default, Iterable):
                mock_names = list(attr.default)
            # Note: If attr.default is None it will connect to None so no need for
            # adding anything mapping of mocks.

            # Populate a mapping of mocks pretending to be the things on the server
            mocks = {}
            for name in mock_names:
                mock = Mock(spec=mock_class)
                mock.name = name
                mocks[name] = mock
                # Store a copy of this mock in the mock server interface so it isn't
                # garbage collected.
                # Note that this causes mypy to throw an  `attr-defined` error as _mock
                # only exists in the MockThingServerInterface
                thing._thing_server_interface._mocks.append(mock)  # type: ignore[attr-defined]

            attr.connect(thing, mocks, ...)
