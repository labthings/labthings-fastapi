"""Code supporting the LabThings server.

LabThings wraps the `fastapi.FastAPI` application in a `.ThingServer`, which
provides the tools to serve and manage `.Thing` instances.

See the :ref:`tutorial` for examples of how to set up a `.ThingServer`.
"""

from __future__ import annotations
from typing import AsyncGenerator, Optional, TypeVar
from typing_extensions import Self
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from anyio.from_thread import BlockingPortal
from contextlib import asynccontextmanager, AsyncExitStack
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from ..middleware.url_for import url_for_middleware
from ..thing_slots import ThingSlot
from ..utilities import class_attributes

from ..actions import ActionManager
from ..logs import configure_thing_logger
from ..thing import Thing
from ..thing_server_interface import ThingServerInterface
from ..thing_description._model import ThingDescription
from ..dependencies.thing_server import _thing_servers  # noqa: F401
from .config_model import (
    ThingsConfig,
    ThingServerConfig,
    normalise_things_config as normalise_things_config,
)

# `_thing_servers` is used as a global from `ThingServer.__init__`
from ..outputs.blob import blob_data_manager

__all__ = ["ThingServer"]


ThingSubclass = TypeVar("ThingSubclass", bound=Thing)


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

    def __init__(
        self,
        things: ThingsConfig,
        settings_folder: Optional[str] = None,
    ) -> None:
        r"""Initialise a LabThings server.

        Setting up the `.ThingServer` involves creating the underlying
        `fastapi.FastAPI` app, setting its lifespan function (used to
        set up and shut down the `.Thing` instances), and configuring it
        to allow cross-origin requests.

        We also create the `.ActionManager` to manage :ref:`actions` and the
        `.BlobManager` to manage the downloading of :ref:`blobs`.

        :param things: A mapping of Thing names to `.Thing` subclasses, or
            `.ThingConfig` objects specifying the subclass, its initialisation
            arguments, and any connections to other `.Thing`\ s.
        :param settings_folder: the location on disk where `.Thing`
            settings will be saved.
        """
        self.startup_failure: dict | None = None
        configure_thing_logger()  # Note: this is safe to call multiple times.
        self._config = ThingServerConfig(things=things, settings_folder=settings_folder)
        self.app = FastAPI(lifespan=self.lifespan)
        self._set_cors_middleware()
        self._set_url_for_middleware()
        self.settings_folder = settings_folder or "./settings"
        self.action_manager = ActionManager()
        self.action_manager.attach_to_app(self.app)
        blob_data_manager.attach_to_app(self.app)
        self._add_things_view_to_app()
        self.blocking_portal: Optional[BlockingPortal] = None
        self.startup_status: dict[str, str | dict] = {"things": {}}
        global _thing_servers  # noqa: F824
        _thing_servers.add(self)
        # The function calls below create and set up the Things.
        self._things = self._create_things()
        self._connect_things()
        self._attach_things_to_server()

    @classmethod
    def from_config(cls, config: ThingServerConfig) -> Self:
        r"""Create a ThingServer from a configuration model.

        This is equivalent to ``ThingServer(**dict(config))``\ .

        :param config: The configuration parameters for the server.
        :return: A `.ThingServer` configured as per the model.
        """
        return cls(**dict(config))

    def _set_cors_middleware(self) -> None:
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

    def _set_url_for_middleware(self) -> None:
        """Add middleware to support `url_for` in Pydantic models.

        This middleware adds a request state variable that allows
        `labthings_fastapi.server.URLFor` instances to be serialised
        using FastAPI's `url_for` function.
        """
        self.app.middleware("http")(url_for_middleware)

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

    def path_for_thing(self, name: str) -> str:
        """Return the path for a thing with the given name.

        :param name: The name of the thing.

        :return: The path at which the thing is served.

        :raise KeyError: if no thing with the given name has been added.
        """
        if name not in self._things:
            raise KeyError(f"No thing named {name} has been added to this server.")
        return f"/{name}/"

    def _create_things(self) -> Mapping[str, Thing]:
        r"""Create the Things, add them to the server, and connect them up if needed.

        This method is responsible for creating instances of `.Thing` subclasses
        and adding them to the server. It also ensures the `.Thing`\ s are connected
        together if required.

        The Things are defined in ``self._config.thing_configs`` which in turn is
        generated from the ``things`` argument to ``__init__``\ .

        :return: A mapping of names to `.Thing` instances.

        :raise TypeError: if ``cls`` is not a subclass of `.Thing`.
        """
        things: dict[str, Thing] = {}
        for name, config in self._config.thing_configs.items():
            if not issubclass(config.cls, Thing):
                raise TypeError(f"{config.cls} is not a Thing subclass.")
            interface = ThingServerInterface(name=name, server=self)
            os.makedirs(interface.settings_folder, exist_ok=True)
            # This is where we instantiate the Thing
            things[name] = config.cls(
                *config.args,
                **config.kwargs,
                thing_server_interface=interface,
            )
        return things

    def _connect_things(self) -> None:
        r"""Connect the `thing_slot` attributes of Things.

        A `.Thing` may have attributes defined as ``lt.thing_slot()``, which
        will be populated after all `.Thing` instances are loaded on the server.

        This function is responsible for supplying the `.Thing` instances required
        for each connection. This will be done by using the name specified either
        in the connection's default, or in the configuration of the server.

        `.ThingSlotError` will be raised by code called by this method if
        the connection cannot be provided. See `.ThingSlot.connect` for more
        details.
        """
        for thing_name, thing in self.things.items():
            config = self._config.thing_configs[thing_name].thing_slots
            for attr_name, attr in class_attributes(thing):
                if not isinstance(attr, ThingSlot):
                    continue
                target = config.get(attr_name, ...)
                attr.connect(thing, self.things, target)

    def _attach_things_to_server(self) -> None:
        """Add the Things to the FastAPI App.

        This calls `.Thing.attach_to_server` on each `.Thing` that is a part of
        this `.ThingServer` in order to add the HTTP endpoints and load settings.
        """
        for thing in self.things.values():
            thing.attach_to_server(self)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI) -> AsyncGenerator[None, None]:
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
        :raises BaseException: Reraises any errors that are caught when calling
            ``__enter__`` on each Thing. The error is also saved to
            ``self.startup_failure`` for post mortem, as otherwise uvicorn will swallow
            it and replace it with SystemExit(3) and no traceback.
        """
        async with BlockingPortal() as portal:
            # We create a blocking portal to allow threaded code to call async code
            # in the event loop.
            self.blocking_portal = portal

            # we __aenter__ and __aexit__ each Thing, which will in turn call the
            # synchronous __enter__ and __exit__ methods if they exist, to initialise
            # and shut down the hardware. NB we must make sure the blocking portal
            # is present when this happens, in case we are dealing with threads.
            async with AsyncExitStack() as stack:
                for thing in self.things.values():
                    try:
                        await stack.enter_async_context(thing)
                    except BaseException as e:
                        self.startup_failure = {
                            "thing": thing.name,
                            "exception": e,
                        }
                        raise
                yield

        self.blocking_portal = None

    def _add_things_view_to_app(self) -> None:
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
                name: thing.thing_description(name + "/", base=str(request.base_url))
                for name, thing in thing_server.things.items()
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
