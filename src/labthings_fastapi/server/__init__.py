"""Code supporting the LabThings server.

LabThings wraps the `fastapi.FastAPI` application in a `.ThingServer`, which
provides the tools to serve and manage `.Thing` instances.

See the :ref:`tutorial` for examples of how to set up a `.ThingServer`.
"""

from __future__ import annotations
from typing import Any, AsyncGenerator, Optional, Sequence, TypeVar
import os.path
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from anyio.from_thread import BlockingPortal
from contextlib import asynccontextmanager, AsyncExitStack
from collections.abc import Mapping
from types import MappingProxyType

from ..utilities.object_reference_to_object import (
    object_reference_to_object,
)
from ..actions import ActionManager
from ..thing import Thing
from ..thing_description._model import ThingDescription
from ..dependencies.thing_server import _thing_servers  # noqa: F401

# `_thing_servers` is used as a global from `ThingServer.__init__`
from ..outputs.blob import BlobDataManager

# A path should be made up of names separated by / as a path separator.
# Each name should be made of alphanumeric characters, hyphen, or underscore.
# This regex enforces a trailing /
PATH_REGEX = re.compile(r"^/([a-zA-Z0-9\-_]+\/)+$")


class ThingServer:
    """Use FastAPI to serve `.Thing` instances.

    The `.ThingServer` sets up a `fastapi.FastAPI` application and uses it
    to expose the capabilities of `.Thing` instances over HTTP.

    There are several functions of a `.ThingServer`:

    * Manage where settings are stored, to allow `.Thing` instances to
      load and save their settings from disk.
    * Configure the server to allow cross-origin requests (required if
      we use a web app that is not served from the `.ThingServer`).
    * Manage the threads used to run :ref:`actions`.
    * Manage :ref:`blobs` to allow binary data to be returned.
    * Allow threaded code to call functions in the event loop, by providing
      an `anyio.from_thread.BlockingPortal`.
    """

    def __init__(self, settings_folder: Optional[str] = None) -> None:
        """Initialise a LabThings server.

        Setting up the `.ThingServer` involves creating the underlying
        `fastapi.FastAPI` app, setting its lifespan function (used to
        set up and shut down the `.Thing` instances), and configuring it
        to allow cross-origin requests.

        We also create the `.ActionManager` to manage :ref:`actions` and the
        `.BlobManager` to manage the downloading of :ref:`blobs`.

        :param settings_folder: the location on disk where `.Thing`
            settings will be saved.
        """
        self.app = FastAPI(lifespan=self.lifespan)
        self.set_cors_middleware()
        self.settings_folder = settings_folder or "./settings"
        self.action_manager = ActionManager()
        self.action_manager.attach_to_app(self.app)
        self.blob_data_manager = BlobDataManager()
        self.blob_data_manager.attach_to_app(self.app)
        self.add_things_view_to_app()
        self._things: dict[str, Thing] = {}
        self.blocking_portal: Optional[BlockingPortal] = None
        self.startup_status: dict[str, str | dict] = {"things": {}}
        global _thing_servers  # noqa: F824
        _thing_servers.add(self)

    app: FastAPI
    action_manager: ActionManager
    blob_data_manager: BlobDataManager

    def set_cors_middleware(self) -> None:
        """Configure the server to allow requests from other origins.

        This is required to allow web applications access to the HTTP API,
        if they are not served from the same origin (i.e. if they are not
        served as part of the `.ThingServer`.).

        This is usually needed during development, and may be needed at
        other times depending on how you are using LabThings.
        """
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @property
    def things(self) -> Mapping[str, Thing]:
        """Return a dictionary of all the things.

        :return: a dictionary mapping thing paths to `.Thing` instances.
        """
        return MappingProxyType(self._things)

    ThingInstance = TypeVar("ThingInstance", bound=Thing)

    def things_by_class(self, cls: type[ThingInstance]) -> Sequence[ThingInstance]:
        """Return all Things attached to this server matching a class.

        Return all instances of ``cls`` attached to this server.

        :param cls: A `.Thing` subclass.

        :return: all instances of ``cls`` that have been added to this server.
        """
        return [t for t in self.things.values() if isinstance(t, cls)]

    def thing_by_class(self, cls: type[ThingInstance]) -> ThingInstance:
        """Return the instance of ``cls`` attached to this server.

        This function calls `.ThingServer.things_by_class`, but asserts that
        there is exactly one match.

        :param cls: a `.Thing` subclass.

        :return: the instance of ``cls`` attached to this server.

        :raise RuntimeError: if there is not exactly one matching Thing.
        """
        instances = self.things_by_class(cls)
        if len(instances) == 1:
            return instances[0]
        raise RuntimeError(
            f"There are {len(instances)} Things of class {cls}, expected 1."
        )

    def add_thing(
        self,
        name: str,
        thing_subclass: type[Thing],
        args: Sequence[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Add a thing to the server.

        :param name: The name to use for the thing. This will be part of the URL
            used to access the thing, and must only contain alphanumeric characters,
            hyphens and underscores.
        :param thing_subclass: The `.Thing` subclass to add to the server.
        :param kwargs: keyword arguments to pass to the constructor of
            ``thing_subclass``.

        :raise ValueError: if ``path`` contains invalid characters.
        :raise KeyError: if a `.Thing` has already been added at ``path``.
        :raise TypeError: if ``thing_subclass`` is not a subclass of `.Thing`.
        """
        if PATH_REGEX.match(name) is None:
            msg = (
                f"'{name}' contains unsafe characters. Use only alphanumeric "
                "characters, hyphens and underscores"
            )
            raise ValueError(msg)
        if name in self._things:
            raise KeyError(f"{name} has already been added to this thing server.")
        if not issubclass(thing_subclass, Thing):
            raise TypeError(f"{thing_subclass} is not a Thing subclass.")
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        # This is where we instantiate the Thing
        thing = thing_subclass(*args, **kwargs)
        self._things[name] = thing
        settings_folder = os.path.join(self.settings_folder, name)
        os.makedirs(settings_folder, exist_ok=True)
        thing.attach_to_server(
            server=self,
            path=self.path_for_thing(name),
            setting_storage_path=os.path.join(settings_folder, "settings.json"),
        )

    def path_for_thing(self, name: str) -> str:
        """Return the path for a thing with the given name.

        :param name: The name of the thing, as passed to `.add_thing`.

        :return: The path at which the thing is served.

        :raise KeyError: if no thing with the given name has been added.
        """
        if name not in self._things:
            raise KeyError(f"No thing named {name} has been added to this server.")
        return f"/{name}/"

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncGenerator[None]:
        """Manage set up and tear down of the server and Things.

        This method is used as a lifespan function for the FastAPI app. See
        the lifespan_ page in FastAPI's documentation.

        .. _lifespan: https://fastapi.tiangolo.com/advanced/events/#lifespan-function

        This does two important things:

        * It sets up the blocking portal so background threads can run async code
          (this is required for events, streams, etc.).
        * It runs setup/teardown code for Things by calling them as context
          managers.

        :param app: The FastAPI application wrapped by the server.
        :yield: no value. The FastAPI application will serve requests while this
            function yields.

        :raises RuntimeError: if a `.Thing` already has a blocking portal attached.
            This should never happen, and suggests the server is being used to
            serve a `.Thing` that is already being served elsewhere.
        """
        async with BlockingPortal() as portal:
            self.blocking_portal = portal
            # We attach a blocking portal to each thing, so that threaded code can
            # make callbacks to async code (needed for events etc.)
            for thing in self.things.values():
                if thing._labthings_blocking_portal is not None:
                    raise RuntimeError("Things may only ever have one blocking portal")
                thing._labthings_blocking_portal = portal
            # we __aenter__ and __aexit__ each Thing, which will in turn call the
            # synchronous __enter__ and __exit__ methods if they exist, to initialise
            # and shut down the hardware. NB we must make sure the blocking portal
            # is present when this happens, in case we are dealing with threads.
            async with AsyncExitStack() as stack:
                for thing in self.things.values():
                    await stack.enter_async_context(thing)
                yield
            for _name, thing in self.things.items():
                # Remove the blocking portal - the event loop is about to stop.
                thing._labthings_blocking_portal = None

        self.blocking_portal = None

    def add_things_view_to_app(self) -> None:
        """Add an endpoint that shows the list of attached things."""
        thing_server = self

        @self.app.get(
            "/thing_descriptions/",
            response_model_exclude_none=True,
            response_model_by_alias=True,
        )
        def thing_descriptions(request: Request) -> Mapping[str, ThingDescription]:
            """Describe all the things available from this server.

            This returns a dictionary, where the keys are the paths to each
            `.Thing` attached to the server, and the values are :ref:`wot_td` documents
            represented as `.ThingDescription` objects. These should enable
            clients to see all the capabilities of the `.Thing` instances and
            access them over HTTP.

            :param request: is supplied automatically by FastAPI.

            :return: a dictionary mapping Thing paths to :ref:`wot_td` objects, which
                are `pydantic.BaseModel` subclasses that get serialised to
                dictionaries.
            """
            return {
                path: thing.thing_description(path, base=str(request.base_url))
                for path, thing in thing_server.things.items()
            }

        @self.app.get("/things/")
        def thing_paths(request: Request) -> Mapping[str, str]:
            """URLs pointing to the Thing Descriptions of each Thing.

            :param request: is supplied automatically by FastAPI.

            :return: a list of paths pointing to `.Thing` instances. These
                URLs will return the :ref:`wot_td` of one `.Thing` each.
            """  # noqa: D403 (URLs is correct capitalisation)
            return {
                t: f"{str(request.base_url).rstrip('/')}{t}"
                for t in thing_server.things.keys()
            }


def server_from_config(config: dict) -> ThingServer:
    r"""Create a ThingServer from a configuration dictionary.

    This function creates a `.ThingServer` and adds a number of `.Thing`
    instances from a configuration dictionary.

    :param config: A dictionary, in the format used by :ref:`config_files`

    :return: A `.ThingServer` with instances of the specified `.Thing`
        subclasses attached. The server will not be started by this
        function.

    :raise ImportError: if a Thing could not be loaded from the specified
        object reference.
    :raise TypeError: if a class is specified that does not subclass `.Thing`\ .
    """
    server = ThingServer(config.get("settings_folder", None))
    for name, thing in config.get("things", {}).items():
        if isinstance(thing, str):
            thing = {"class": thing}
        try:
            cls = object_reference_to_object(thing["class"])
        except ImportError as e:
            raise ImportError(
                f"Could not import {thing['class']}, which was "
                f"specified as the class for {name}."
            ) from e
        instance = cls(*thing.get("args", {}), **thing.get("kwargs", {}))
        if not isinstance(instance, Thing):
            raise TypeError(f"{thing['class']} is not a Thing")
        server.add_thing(
            name=name,
            thing_subclass=cls,
            args=thing.get("args", ()),
            kwargs=thing.get("kwargs", {}),
        )
    return server
