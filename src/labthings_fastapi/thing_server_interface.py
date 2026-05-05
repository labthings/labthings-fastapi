r"""Interface between `~lt.Thing` subclasses and the `~lt.ThingServer`\ ."""

from __future__ import annotations
from collections.abc import Iterator
from concurrent.futures import Future
from contextlib import contextmanager
from copy import deepcopy
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Mapping,
    ParamSpec,
    TypeVar,
)
from weakref import ref, ReferenceType

from labthings_fastapi.global_lock import GlobalLock

from .exceptions import FeatureNotEnabledError, ServerNotRunningError

if TYPE_CHECKING:
    from .server import ThingServer
    from .actions import ActionManager


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

    This is added to every `~lt.Thing` during ``__init__`` and is available
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

        :param server: the `~lt.ThingServer` instance we're connected to.
            This will be retained as a weak reference.
        :param name: the name of the `~lt.Thing` instance this interface
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

    def call_async_task(
        self, async_function: Callable[Params, Awaitable[ReturnType]], *args: Any
    ) -> ReturnType:
        r"""Run an asynchronous task in the server's event loop in a blocking manner.

        This function wraps `anyio.from_thread.BlockingPortal.call` to
        provide a way of calling asynchronous code from threaded code. It will
        block the current thread while it calls the provided async function in the
        server's event loop.

        Do not call this from the event loop or it may lead to a deadlock.

        :param async_function: the asynchronous function to call.
        :param \*args: positional arguments to be provided to the function.

        :returns: The return value from the asynchronous function.

        :raises ServerNotRunningError: if the server is not running
            (i.e. there is no event loop).
        """
        portal = self._get_server().blocking_portal
        if portal is None:
            raise ServerNotRunningError("Can't run async code without an event loop.")
        return portal.call(async_function, *args)

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

    @property
    def application_config(self) -> Mapping[str, Any] | None:
        """The custom application configuration options from configuration."""
        return deepcopy(self._get_server().application_config)

    def get_thing_states(self) -> Mapping[str, Any]:
        """Retrieve metadata from all Things on the server.

        This function will retrieve the `~lt.Thing.thing_state` property from
        each `~lt.Thing` on the server, and return it as a dictionary.
        It is intended to make it easy to add metadata to the results
        of actions, for example to embed in an image.

        :return: a dictionary of metadata, with the `~lt.Thing` names as keys.
        """
        return {k: v.thing_state for k, v in self._get_server().things.items()}

    @property
    def _action_manager(self) -> ActionManager:
        """The ActionManager for the Thing attached to this interface.

        This property may be removed in future, and is for internal use only.
        """
        return self._get_server().action_manager

    @property
    def global_lock(self) -> GlobalLock | None:
        r"""A lock that ensures property writes and actions are one-at-a-time.

        If global locking is not enabled, this property will return None.
        """
        return self._get_server().global_lock

    @contextmanager
    def _optionally_hold_global_lock(
        self, enabled: bool | None = True
    ) -> Iterator[None]:
        """Hold the global lock, if required, as a context manager.

        This function will hold the global lock if necessary while a block of code runs.
        Its behaviour is controlled by the `enabled` parameter: if `enabled` is `False`
        this function does nothing. If it is `None` (the default when called from a
        property or action that's not otherwise configured), the global lock is
        held if it exists, but no error is raised if global locking is disabled.

        If ``enabled`` is `True` (the default if no arguments are passed), an error
        will be raised if there is no global lock.

        :param enabled: whether to use the global lock. `True` and `False` have the
            obvious meanings described above, `None` will use the lock if it is enabled
            globally but won't raise an error if it is unavailable.
        :raises FeatureNotEnabledError: if `enabled` is `True` but the global lock is
            not enabled.
        """
        if self.global_lock is None:
            if enabled is True:
                msg = "The global lock is required, but is not enabled."
                raise FeatureNotEnabledError(msg)
            # If we get here, the global lock is disabled so we do nothing.
            yield
        else:
            if enabled is False:  # The lock is being explicitly skipped
                yield
            else:
                with self.global_lock:
                    yield

    @contextmanager
    def hold_global_lock(self, *, error_if_unavailable: bool = True) -> Iterator[None]:
        """Hold the global lock for the duration of a with block.

        This context manager will hold the global lock while a ``with:`` block runs.
        By default, an exception will be raised if the global lock is not enabled.

        :param error_if_unavailable: may be set to `False` to suppress errors if the
            global lock is not enabled. This means the context manager silently does
            nothing, if the global lock is not available.
        """
        with self._optionally_hold_global_lock(True if error_if_unavailable else None):
            yield
