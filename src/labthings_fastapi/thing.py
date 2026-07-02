"""A class to represent hardware or software Things.

The `~lt.Thing` class enables most of the functionality of this library,
and is the way in to most of its features. See :ref:`structure`
for how it fits with the rest of the library.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from json.decoder import JSONDecodeError
from typing import TYPE_CHECKING, Any, Optional

from anyio.to_thread import run_sync
from fastapi import Request, WebSocket
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from typing_extensions import Self

from labthings_fastapi.actions import ActionCollection
from labthings_fastapi.base_descriptor import OptionallyBoundDescriptor
from labthings_fastapi.invocation_contexts import get_invocation_id
from labthings_fastapi.logs import THING_LOGGER
from labthings_fastapi.properties import (
    PropertyCollection,
    SettingCollection,
)
from labthings_fastapi.thing_class_settings import (
    ThingClassSettings,
    validate_thing_class_settings,
)
from labthings_fastapi.thing_description import validation
from labthings_fastapi.thing_description._model import (
    NoSecurityScheme,
    ThingDescription,
)
from labthings_fastapi.thing_server_interface import ThingServerInterface
from labthings_fastapi.utilities import class_attributes
from labthings_fastapi.utilities.introspection import get_docstring, get_summary
from labthings_fastapi.websockets import websocket_endpoint

if TYPE_CHECKING:
    from labthings_fastapi.actions import ActionManager
    from labthings_fastapi.server import ThingServer


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
    *   Properties and Actions are defined using decorators: the :deco:`lt.action`
        decorator declares a method to be an action, which will run when it's triggered,
        and the :deco:`~lt.property` decorator does the same for a property.

        Properties may also be defined using dataclass-style syntax, if they do
        not need getter and setter functions.

        See the documentation on those functions for more detail.
    *   `title` will be used in various places as the human-readable name of your Thing,
        so it makes sense to set this in a subclass.

    There are various LabThings methods that you should avoid overriding unless you
    know what you are doing: anything not mentioned above that's defined in `Thing`
    is probably best left alone.
    """

    title: str
    """A human-readable description of the Thing"""

    _class_settings: ThingClassSettings
    r"""A dictionary of settings that affect how the Thing subclass works.

    Valid keys are listed below:

    ``validate_properties_on_set`` `bool`
        If this key is set to `True`\ , property values will be validated when they are
        set by Python code, as well as when they are set over HTTP. Currently, the
        default behaviour is only to validate values sent over HTTP, not set directly
        in Python. It is likely that validation in both cases will happen by default in
        a future release.

    .. note::

        Class settings must not be changed after the class is defined.
    """

    _thing_server_interface: ThingServerInterface
    """Provide access to features of the server that this `Thing` is attached to."""

    def __init__(self, thing_server_interface: ThingServerInterface) -> None:
        """Initialise a Thing.

        The most important function of ``__init__`` is attaching the
        thing_server_interface, and setting the path. Note that `Thing`
        instances are usually created by a `~lt.ThingServer` and not instantiated
        directly: if you do make a `Thing` directly, you will need to supply
        a `~lt.ThingServerInterface` that is connected to a `~lt.ThingServer` or a
        suitable mock object.

        :param thing_server_interface: The interface to the server that
            is hosting this Thing. It will be supplied when the `Thing` is
            instantiated by the `~lt.ThingServer` or by
            `.create_thing_without_server` which generates a mock interface.
        """
        self._thing_server_interface = thing_server_interface
        # Prevent settings being saved before the file has been loaded.
        # This fixes #383, where writing to a setting during __init__
        # overwrote the settings file with default values.
        self._disable_saving_settings: bool = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        r"""Validate the class settings.

        :param \**kwargs: are passed to the superclass.
        """
        super().__init_subclass__(**kwargs)
        validate_thing_class_settings(cls)

    @property
    def path(self) -> str:
        """The path at which the `~lt.Thing` is exposed over HTTP."""
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

        Attaching the `~lt.Thing` to a `~lt.ThingServer` allows the `~lt.Thing` to start
        actions, load its settings from the correct place, and create HTTP endpoints
        to allow it to be accessed from the HTTP API.

        We create HTTP endpoints for all :ref:`wot_affordances` on the `Thing`, as well
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
            name=f"things.{self.name}",
            summary=get_summary(self.thing_description),
            description=get_docstring(self.thing_description),
            response_model_exclude_none=True,
            response_model_by_alias=True,
        )
        def thing_description(request: Request) -> ThingDescription:
            return self.thing_description(base=str(request.base_url))

        @server.app.websocket(self.path + "ws")
        async def websocket(ws: WebSocket) -> None:
            await websocket_endpoint(self, ws, server.message_broker)

    def _read_settings_file(self) -> Mapping[str, Any] | None:
        """Read the settings file and return a mapping of saved settings or None.

        This function handles reading the settings from the disk. It is designed
        to be called by `load_settings`. Any exceptions caused by file handling or
        file corruption are caught and logged as warnings.

        :return: A Mapping of setting name to setting value, or None if no settings
            could be read from file.
        """
        setting_storage_path = self._thing_server_interface.settings_file_path
        thing_name = type(self).__name__
        if not os.path.exists(setting_storage_path):
            # If the settings file doesn't exist, we have nothing to do - the settings
            # are already initialised to their default values.
            return None

        # Load the settings.
        try:
            with open(setting_storage_path, "r", encoding="utf-8") as file_obj:
                settings = json.load(file_obj)
        except (FileNotFoundError, PermissionError, JSONDecodeError):
            # Note that if the settings file is missing, we should already have
            # returned before attempting to load settings.
            self.logger.warning(
                "Error loading settings for %s from %s, could not load a JSON "
                "object. Settings for this Thing will be reset to default.",
                thing_name,
                setting_storage_path,
            )
            return None

        if not isinstance(settings, Mapping):
            self.logger.warning(
                "Error loading settings for %s from %s. The file does not contain a "
                "Mapping",
                thing_name,
                setting_storage_path,
            )
            return None

        # The settings are loaded and are a Mapping. Return them.
        return settings

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
        settings = self._read_settings_file()
        if settings is None:
            # If no settings were read, we don't need to update their values.
            # We should, however, allow the settings file to be saved, as we
            # have established that we're not going to overwrite anything of
            # value.
            self._disable_saving_settings = False
            return

        # Stop recursion by not allowing settings to be saved as we're reading them.
        self._disable_saving_settings = True
        try:
            for name, value in settings.items():
                try:
                    setting = self.settings[name]
                    # Load the key from the JSON file using the setting's model
                    setting.set(setting.validate(value))
                except ValidationError:
                    self.logger.warning(
                        f"Could not load setting {name} from settings file "
                        f"because of a validation error.",
                        exc_info=True,
                    )
                except KeyError:
                    self.logger.warning(
                        f"An extra key {name} was found in the settings file. "
                        "It will be deleted the next time settings are saved."
                    )
        finally:
            self._disable_saving_settings = False

    def save_settings(self) -> None:
        """Save settings to JSON.

        This is called whenever a setting is updated. All settings are written to
        the settings file every time.
        """
        if self._disable_saving_settings:
            return
        # We dump to a string first, to avoid corrupting the file if it fails
        setting_json = self.settings.model_instance.model_dump_json(indent=4)
        path = self._thing_server_interface.settings_file_path
        with open(path, "w", encoding="utf-8") as file_obj:
            file_obj.write(setting_json)

    properties: OptionallyBoundDescriptor["Thing", PropertyCollection] = (
        OptionallyBoundDescriptor(PropertyCollection)
    )
    r"""Access to metadata and functions of this `~lt.Thing`\ 's properties.

    `~lt.Thing.properties` is a mapping of names to `.PropertyInfo` objects, which
    allows convenient access to the metadata related to its properties. Note that
    this includes settings, as they are a subclass of properties.
    """

    settings: OptionallyBoundDescriptor["Thing", SettingCollection] = (
        OptionallyBoundDescriptor(SettingCollection)
    )
    r"""Access to settings-related metadata and functions.

    `~lt.Thing.settings` is a mapping of names to `.SettingInfo` objects that allows
    convenient access to metadata of the settings of this `~lt.Thing`\ .
    """

    actions: OptionallyBoundDescriptor["Thing", ActionCollection] = (
        OptionallyBoundDescriptor(ActionCollection)
    )
    r"""Access to metadata for the actions of this `~lt.Thing`\ .

    `~lt.Thing.actions` is a mapping of names to `.ActionInfo` objects that allows
    convenient access to metadata of each action.
    """

    _labthings_thing_state: Optional[dict] = None

    @property
    def thing_state(self) -> Mapping:
        """A dictionary summarising our current state.

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
            description=self.__doc__,
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

        See `~lt.Thing.thing_description`\ . This function converts the
        return value of that function into a simple dictionary.

        :param path: the URL pointing to this Thing.
        :param base: the base URL for all URLs in the thing description.

        :return: a Thing Description.
        """
        td: ThingDescription = self.thing_description(path=path, base=base)
        td_dict: dict = td.model_dump(exclude_none=True, by_alias=True)
        return jsonable_encoder(td_dict)

    def get_current_invocation_logs(self) -> list[logging.LogRecord]:
        """Get the log records for an on going action.

        This is useful if an action wishes to save its logs alongside any data.

        Note that only the last 1000 logs are returned so for long running tasks that
        log frequently this may want to be read periodically.

        This will error if it is called outside an action invocation.

        :return: a list of all logs from this action.

        :raises RuntimeError: If the server cannot be retrieved. This should never
            happen.
        """
        inv_id = get_invocation_id()
        server = self._thing_server_interface._server()
        if server is None:
            raise RuntimeError("Could not get server from thing_server_interface")
        action_manager = server.action_manager
        this_invocation = action_manager.get_invocation(inv_id)
        return this_invocation.log
