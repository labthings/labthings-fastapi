r"""Interface between `.Thing` subclasses and the `.ThingServer`\ ."""

from __future__ import annotations
from concurrent.futures import Future
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

from anyio.abc import ObjectSendStream

from .exceptions import ServerNotRunningError

if TYPE_CHECKING:
    from .server import ThingServer
    from .actions import ActionManager
    from .events import MessageBroker, Message


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

    def publish(self, message: Message) -> None:
        """Publish an event.

        Use the async event loop to notify websocket subscribers that something has
        happened.

        Note that this function will do nothing if the event loop is not yet running.

        :param affordance: the name of the affordance publishing the event.
        :param message: the message being published.
        """
        try:
            self.start_async_task_soon(self._message_broker.publish, message)
        except ServerNotRunningError:
            pass  # If the server isn't running yet, we can't publish events.

    def subscribe(self, affordance: str, stream: ObjectSendStream[Message]) -> None:
        """Subscribe to events from an affordance.

        Use the async event loop to register a stream to receive events
        from a particular affordance on this Thing.

        :param affordance: the name of the affordance to subscribe to.
        :param stream: the stream to which events should be sent.
        """
        self._message_broker.subscribe(self.name, affordance, stream)

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

    @property
    def _action_manager(self) -> ActionManager:
        """The ActionManager for the Thing attached to this interface.

        This property may be removed in future, and is for internal use only.
        """
        return self._get_server().action_manager

    @property
    def _message_broker(self) -> MessageBroker:
        """The message broker attached to the server.

        This property may be removed in the future, and is for internal use.
        """
        return self._get_server().message_broker
