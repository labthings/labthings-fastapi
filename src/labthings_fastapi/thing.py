"""A class to represent hardware or software Things.

The `.Thing` class enables most of the functionality of this library,
and is the way in to most of its features. See :ref:`structure`
for how it fits with the rest of the library.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional
from typing_extensions import Self
from collections.abc import Mapping
import logging
import os
import json
from json.decoder import JSONDecodeError
from fastapi.encoders import jsonable_encoder
from fastapi import Request, WebSocket
from anyio.abc import ObjectSendStream
from anyio.to_thread import run_sync

from pydantic import BaseModel

from .logs import THING_LOGGER
from .properties import BaseProperty, DataProperty, BaseSetting
from .actions import ActionDescriptor
from .thing_description._model import ThingDescription, NoSecurityScheme
from .utilities import class_attributes
from .thing_description import validation
from .utilities.introspection import get_summary, get_docstring
from .websockets import websocket_endpoint
from .exceptions import PropertyNotObservableError
from .thing_server_interface import ThingServerInterface


if TYPE_CHECKING:
    from .server import ThingServer
    from .actions import ActionManager

_LOGGER = logging.getLogger(__name__)


class Thing:
    r"""Represents a Thing, as defined by the Web of Things standard.

    This class should encapsulate the code that runs a piece of hardware, or provides
    a particular function - it will correspond to a path on the server, and a Thing
    Description document.

    Subclassing Notes
    -----------------

    *   ``__init__``: You should accept any arguments you need to configure the Thing
        in ``__init__``. Don't initialise any hardware at this time, as your Thing may
        be instantiated quite early, or even at import time. You must make sure to
        call ``super().__init__(thing_server_interface)``\ .
    *   ``__enter__(self)`` and ``__exit__(self, exc_t, exc_v, exc_tb)`` are where you
        should start and stop communications with the hardware. This is Python's
        "context manager" protocol. The arguments of ``__exit__`` will be ``None``
        except after errors. You should be safe to ignore them, and just include
        code that will close down your hardware, which is equivalent to a
        ``finally:`` block.
    *   Properties and Actions are defined using decorators: the :deco:`.action`
        decorator declares a method to be an action, which will run when it's triggered,
        and the :deco:`.property` decorator does the same for a property.

        Properties may also be defined using dataclass-style syntax, if they do
        not need getter and setter functions.

        See the documentation on those functions for more detail.
    *   `title` will be used in various places as the human-readable name of your Thing,
        so it makes sense to set this in a subclass.

    There are various LabThings methods that you should avoid overriding unless you
    know what you are doing: anything not mentioned above that's defined in `.Thing` is
    probably best left alone. They may in time be collected together into a single
    object to avoid namespace clashes.
    """

    title: str
    """A human-readable description of the Thing"""

    _thing_server_interface: ThingServerInterface
    """Provide access to features of the server that this `.Thing` is attached to."""

    def __init__(self, thing_server_interface: ThingServerInterface) -> None:
        """Initialise a Thing.

        The most important function of ``__init__`` is attaching the
        thing_server_interface, and setting the path. Note that `.Thing`
        instances are usually created by a `.ThingServer` and not instantiated
        directly: if you do make a `.Thing` directly, you will need to supply
        a `.ThingServerInterface` that is connected to a `.ThingServer` or a
        suitable mock object.

        :param thing_server_interface: The interface to the server that
            is hosting this Thing. It will be supplied when the `.Thing` is
            instantiated by the `.ThingServer` or by
            `.create_thing_without_server` which generates a mock interface.
        """
        self._thing_server_interface = thing_server_interface
        self._disable_saving_settings: bool = False

    @property
    def path(self) -> str:
        """The path at which the `.Thing` is exposed over HTTP."""
        return self._thing_server_interface.path

    @property
    def name(self) -> str:
        """The name of this Thing, as known to the server."""
        return self._thing_server_interface.name

    @property
    def logger(self) -> logging.Logger:
        """A logger, named after this Thing."""
        return THING_LOGGER.getChild(self.name)

    async def __aenter__(self) -> Self:
        """Context management is used to set up/close the thing.

        As things (currently) do everything with threaded code, we define
        async ``__aenter__`` and ``__aexit__`` wrappers to call the synchronous
        code, if it exists.

        :return: this object.
        """
        if hasattr(self, "__enter__"):
            return await run_sync(self.__enter__)
        else:
            return self

    async def __aexit__(
        self, exc_t: Any | None, exc_v: Any | None, exc_tb: Any
    ) -> None:
        """Wrap context management functions, if they exist.

        See ``__aenter__`` for more details.

        :param exc_t: The type of the exception, or ``None``.
        :param exc_v: The exception that occurred, or ``None``.
        :param exc_tb: The traceback for the exception, or ``None``.
        """
        if hasattr(self, "__exit__"):
            await run_sync(self.__exit__, exc_t, exc_v, exc_tb)

    def attach_to_server(self, server: ThingServer) -> None:
        """Attach this thing to the server.

        Things need to be attached to a server before use to function correctly.

        :param server: The server to attach this Thing to.

        Attaching the `.Thing` to a `.ThingServer` allows the `.Thing` to start
        actions, load its settings from the correct place, and create HTTP endpoints
        to allow it to be accessed from the HTTP API.

        We create HTTP endpoints for all :ref:`wot_affordances` on the `.Thing`, as well
        as any `.EndpointDescriptor` descriptors.
        """
        self.action_manager: ActionManager = server.action_manager
        self.load_settings()

        for _name, item in class_attributes(self):
            try:
                item.add_to_fastapi(server.app, self)
            except AttributeError:
                # We try to add everything, and ignore whatever doesn't have
                # an `add_to_fastapi` method.
                # TODO: Do we want to be more choosy about what we add?
                pass

        @server.app.get(
            self.path,
            summary=get_summary(self.thing_description),
            description=get_docstring(self.thing_description),
            response_model_exclude_none=True,
            response_model_by_alias=True,
        )
        def thing_description(request: Request) -> ThingDescription:
            return self.thing_description(base=str(request.base_url))

        @server.app.websocket(self.path + "ws")
        async def websocket(ws: WebSocket) -> None:
            await websocket_endpoint(self, ws)

    # A private variable to hold the list of settings so it doesn't need to be
    # iterated through each time it is read
    _settings_store: Optional[dict[str, BaseSetting]] = None

    @property
    def _settings(self) -> dict[str, BaseSetting]:
        """A private property that returns a dict of all settings for this Thing.

        Each dict key is the name of the setting, the corresponding value is the
        BaseSetting class (a descriptor). This can be used to directly get the
        descriptor so that the value can be set without emitting signals, such
        as on startup.
        """
        if self._settings_store is not None:
            return self._settings_store

        self._settings_store = {}
        for name, attr in class_attributes(self):
            if isinstance(attr, BaseSetting):
                self._settings_store[name] = attr
        return self._settings_store

    def load_settings(self) -> None:
        """Load settings from json.

        Read the JSON file and use it to populate settings.

        .. note::
            Settings are loaded when the Thing is added to a server, so they will
            not be available while the ``__init__`` method is run.

            Note that no notifications will be triggered when the settings are set,
            so if action is needed (e.g. updating hardware with the loaded settings)
            it should be taken in ``__enter__``.
        """
        setting_storage_path = self._thing_server_interface.settings_file_path
        thing_name = type(self).__name__
        if os.path.exists(setting_storage_path):
            self._disable_saving_settings = True
            try:
                with open(setting_storage_path, "r", encoding="utf-8") as file_obj:
                    setting_dict = json.load(file_obj)
                for key, value in setting_dict.items():
                    if key in self._settings:
                        self._settings[key].set_without_emit(self, value)
                    else:
                        _LOGGER.warning(
                            (
                                "Cannot set %s from persistent storage as %s "
                                "has no matching setting."
                            ),
                            key,
                            thing_name,
                        )
            except (FileNotFoundError, JSONDecodeError, PermissionError):
                _LOGGER.warning("Error loading settings for %s", thing_name)
            finally:
                self._disable_saving_settings = False

    def save_settings(self) -> None:
        """Save settings to JSON.

        This is called whenever a setting is updated. All settings are written to
        the settings file every time.
        """
        if self._disable_saving_settings:
            return
        if self._settings is not None:
            setting_dict = {}
            for name in self._settings.keys():
                value = getattr(self, name)
                if isinstance(value, BaseModel):
                    value = value.model_dump()
                setting_dict[name] = value
            # Dumpy to string before writing so if this fails the file isn't overwritten
            setting_json = json.dumps(setting_dict, indent=4)
            path = self._thing_server_interface.settings_file_path
            with open(path, "w", encoding="utf-8") as file_obj:
                file_obj.write(setting_json)

    _labthings_thing_state: Optional[dict] = None

    @property
    def thing_state(self) -> Mapping:
        """Return a dictionary summarising our current state.

        This is intended to be an easy way to collect metadata from a Thing that
        summarises its state. It might be used, for example, to record metadata
        along with each reading/image/etc. when an instrument is saving data.

        It's best to populate this automatically so it can always be accessed. If
        it requires calls e.g. to a serial instrument, bear in mind it may be called
        quite often and shouldn't take too long.

        Some measure of caching here is a nice aim for the future, but not yet
        implemented.
        """
        if self._labthings_thing_state is None:
            self._labthings_thing_state = {}
        return self._labthings_thing_state

    def validate_thing_description(self) -> None:
        """Raise an exception if the thing description is not valid."""
        td = self.thing_description_dict()
        return validation.validate_thing_description(td)

    _cached_thing_description: Optional[
        tuple[Optional[str], Optional[str], ThingDescription]
    ] = None

    def thing_description(
        self, path: Optional[str] = None, base: Optional[str] = None
    ) -> ThingDescription:
        """Generate a w3c Thing Description representing this thing.

        The w3c Web of Things working group defined a standard representation
        of a Thing, which provides a high-level description of the actions,
        properties, and events that it exposes. This endpoint delivers a JSON
        representation of the :ref:`wot_td` for this Thing.

        :param path: the URL pointing to this Thing.
        :param base: the base URL for all URLs in the thing description.

        :return: a Thing Description.
        """
        path = path or getattr(self, "path", "{base_uri}")
        if (
            self._cached_thing_description
            and self._cached_thing_description[0] == path
            and self._cached_thing_description[1] == base
        ):
            return self._cached_thing_description[2]

        properties = {}
        actions = {}
        for name, item in class_attributes(self):
            if hasattr(item, "property_affordance"):
                properties[name] = item.property_affordance(self, path)
            if hasattr(item, "action_affordance"):
                actions[name] = item.action_affordance(self, path)

        td = ThingDescription(
            title=getattr(self, "title", self.__class__.__name__),
            properties=properties,
            actions=actions,
            security="no_security",
            securityDefinitions={"no_security": NoSecurityScheme()},
            base=base,
        )
        self._cached_thing_description = (path, base, td)
        return td

    def thing_description_dict(
        self,
        path: Optional[str] = None,
        base: Optional[str] = None,
    ) -> dict:
        r"""Describe this Thing with a Thing Description as a simple dict.

        See `.Thing.thing_description`\ . This function converts the
        return value of that function into a simple dictionary.

        :param path: the URL pointing to this Thing.
        :param base: the base URL for all URLs in the thing description.

        :return: a Thing Description.
        """
        td: ThingDescription = self.thing_description(path=path, base=base)
        td_dict: dict = td.model_dump(exclude_none=True, by_alias=True)
        return jsonable_encoder(td_dict)

    def observe_property(self, property_name: str, stream: ObjectSendStream) -> None:
        """Register a stream to receive property change notifications.

        :param property_name: the property to register for.
        :param stream: the stream used to send events.

        :raise KeyError: if the requested name is not defined on this Thing.
        :raise PropertyNotObservableError: if the property is not observable.
        """
        prop = getattr(self.__class__, property_name, None)
        if not isinstance(prop, BaseProperty):
            raise KeyError(f"{property_name} is not a LabThings Property")
        if not isinstance(prop, DataProperty):
            raise PropertyNotObservableError(f"{property_name} is not observable.")
        prop._observers_set(self).add(stream)

    def observe_action(self, action_name: str, stream: ObjectSendStream) -> None:
        """Register a stream to receive action status change notifications.

        :param action_name: the action to register for.
        :param stream: the stream used to send events.

        :raise KeyError: if the requested name is not defined on this Thing.
        """
        action = getattr(self.__class__, action_name, None)
        if not isinstance(action, ActionDescriptor):
            raise KeyError(f"{action_name} is not an LabThings Action")
        observers = action._observers_set(self)
        observers.add(stream)
