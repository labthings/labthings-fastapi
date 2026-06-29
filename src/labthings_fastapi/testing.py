"""Test harnesses to help with writitng tests for things.."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from concurrent.futures import Future
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    ParamSpec,
    TypeVar,
)
from unittest.mock import Mock

from labthings_fastapi.global_lock import GlobalLock
from labthings_fastapi.message_broker import Message

from .middleware.url_for import dummy_url_for, set_url_for_context
from .thing_server_interface import ThingServerInterface
from .thing_slots import ThingSlot
from .utilities import class_attributes

if TYPE_CHECKING:
    from .actions import ActionManager
    from .server import ThingServer
    from .thing import Thing

Params = ParamSpec("Params")
ReturnType = TypeVar("ReturnType")


class MockThingServerInterface(ThingServerInterface):
    r"""A mock class that simulates a ThingServerInterface without the server.

    This allows a `~lt.Thing` to be instantiated but not connected to a server.
    The methods normally provided by the server are mocked, specifically:

    * The `name` is set by an argument to `__init__`\ .
    * `start_async_task_soon` silently does nothing, i.e. the async function
      will not be run.
    * The settings folder will either be specified when the class is initialised,
      or a temporary folder will be created.
    * `get_thing_states` will return an empty dictionary.
    """

    def __init__(
        self,
        name: str,
        class_name: str,
        settings_folder: str | None = None,
        enable_global_lock: bool = False,
    ) -> None:
        """Initialise a ThingServerInterface.

        :param name: The name of the Thing we're providing an interface to.
        :param class_name: The name of the class of the Thing, used as part of the
            settings filename.
        :param settings_folder: The location where we should save settings.
            By default, this is a temporary directory.
        :param enable_global_lock: Whether to create a global lock object, to
            mock the server setting of the same name.
        """
        # We deliberately don't call super().__init__(), as it won't work without
        # a server.
        self._name: str = name
        self._settings_tempdir: TemporaryDirectory | None = None
        self._settings_folder = settings_folder
        self._global_lock = GlobalLock() if enable_global_lock else None
        self._mocks: list[Thing] = []
        self._class_name = class_name

    def _get_server(self) -> ThingServer:
        """Raise `NotImplementedError` as this is not mocked.

        :return: the server to which we are connected.
        :raises NotImplementedError: because this function is not mocked.
        """
        raise NotImplementedError("`_get_server` is not mocked.")

    def start_async_task_soon(
        self, async_function: Callable[Params, Awaitable[ReturnType]], *args: Any
    ) -> Future[ReturnType]:
        r"""Do nothing, as there's no event loop to use.

        This returns a `concurrent.futures.Future` object that is already cancelled,
        in order to avoid accidental hangs in test code that attempts to wait for
        the future object to resolve. Cancelling it may cause errors if you need
        the return value.

        If you need the async code to run, it's best to add the `~lt.Thing` to a
        `lt.ThingServer` instead. Using a test client will start an event loop
        in a background thread, and allow you to use a real `~lt.ThingServerInterface`
        without the overhead of actually starting an HTTP server.

        :param async_function: the asynchronous function to call.
        :param \*args: positional arguments to be provided to the function.

        :returns: a `concurrent.futures.Future` object that has been cancelled.
        """
        f: Future[ReturnType] = Future()
        f.cancel()
        return f

    def publish(self, message: Message) -> None:
        """Silently ignore published events.

        :param message: a message to publish.
        """

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

    @property
    def _action_manager(self) -> ActionManager:
        """Raise an error, as there's no action manager without a server.

        :raises NotImplementedError: always.
        """
        raise NotImplementedError("MockThingServerInterface has no ActionManager.")

    @property
    def application_config(self) -> None:
        """An empty application configuration when mocking.

        :return: None
        """
        return None

    @property
    def global_lock(self) -> GlobalLock | None:
        """A global lock."""
        return self._global_lock


ThingSubclass = TypeVar("ThingSubclass", bound="Thing")


def create_thing_without_server(
    cls: type[ThingSubclass],
    *args: Any,
    settings_folder: str | None = None,
    mock_all_slots: bool = False,
    enable_global_lock: bool = True,
    **kwargs: Any,
) -> ThingSubclass:
    r"""Create a `~lt.Thing` and supply a mock ThingServerInterface.

    This function is intended for use in testing, where it will enable a `~lt.Thing`
    to be created without a server, by supplying a `.MockThingServerInterface`
    instead of a real `~lt.ThingServerInterface`\ .

    The name of the Thing will be taken from the class name, lowercased.

    :param cls: The `~lt.Thing` subclass to instantiate.
    :param \*args: positional arguments to ``__init__``.
    :param settings_folder: The path to the settings folder. A temporary folder
        is used by default.
    :param mock_all_slots: Set to True to create a `unittest.mock.Mock` object
        connected to each thing slot. It follows the default of the specified
        to the slot. So if an optional slot has a default of `None`, no mock
        will be provided.
    :param enable_global_lock: Whether a global lock should be provided.
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

    msi = MockThingServerInterface(
        name=name,
        class_name=cls.__name__,
        settings_folder=settings_folder,
        enable_global_lock=enable_global_lock,
    )
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


def mock_thing_instance(spec: type[ThingSubclass]) -> ThingSubclass:
    """Create a mock Thing instance, with some important attributes.

    This provides ``__name__``, ``__module__``, and ``_thing_server_interface``
    properties that work correctly, which is convenient when mocking `lt.thing_slot`
    connections.

    :param spec: the Thing subclass we're mocking an instance of. Pass
        `lt.Thing` if it doesn't matter.
    :return: a Mock instance that pretends to be an instance of `spec`.
    """
    mock = Mock(spec=spec)
    mock.__name__ = "Mock{spec.__name__}"
    mock.name = mock.__name__.lower()
    mock.__module__ = "mock_module"
    mock._thing_server_interface = MockThingServerInterface(mock.name, mock.__name__)
    return mock


def _mock_slots(thing: Thing) -> None:
    """Mock the slots of a thing created by create_thing_without_server.

    :param thing: The thing to mock the slots of.
    :raises TypeError: If this was called on a Thing with a real ThingServerInterface
    """
    # Populate a mapping of mocks pretending to be the things on the server
    mocks = {}
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

            # Add mock to dictionary
            for name in mock_names:
                mock = Mock(spec=mock_class)
                mock.name = name
                mocks[name] = mock
                # Store a copy of this mock in the mock server interface so it isn't
                # garbage collected.
                interface = thing._thing_server_interface
                if isinstance(interface, MockThingServerInterface):
                    interface._mocks.append(mock)
                else:
                    raise TypeError(
                        "Slots may not be mocked when a Thing is attached to a real "
                        "server."
                    )

    # Finally connect the mocked slots.
    for _attr_name, attr in class_attributes(thing):
        if isinstance(attr, ThingSlot):
            attr.connect(thing, mocks, ...)


@contextmanager
def use_dummy_url_for() -> Iterator[None]:
    """Use the dummy URL for function in the context variable."""
    with set_url_for_context(dummy_url_for):
        yield


def manually_connect_thing_slot(
    host: Thing,
    slot_name: str,
    target: Thing | Sequence[Thing],
) -> None:
    """Manually connect a thing_slot.

    This will accept either a single `Thing` instance or a sequence
    of `Thing` instances. If `Mock` instances are used, note that they
    must pass an `isinstance` test, so should use the ``spec`` argument
    to specify the correct class for the `~lt.thing_slot` being mocked.
    Mock instances must also provide a unique ``name`` attribute.

    :param host: the `~lt.Thing` on which the slot is defined.
    :param slot_name: the name of the `~lt.thing_slot`.
    :param target: the `~lt.Thing` or sequence of Things it should be connected to.
        If a sequence of multiple Thing are passed, their names are used to create a
        mapping.
    :raises KeyError: if multiple targets are specified, but they do not
        have unique names.
    """
    if not isinstance(target, Sequence):
        names: str | Sequence[str] = target.name
        things = {target.name: target}
    else:
        names = [t.name for t in target]
        if len(set(names)) != len(names):
            msg = f"Thing slot targets {names} are not uniquely named."
            raise KeyError(msg)
        things = {t.name: t for t in target}
    slot = getattr(host.__class__, slot_name)
    slot.connect(host, target=names, things=things)
