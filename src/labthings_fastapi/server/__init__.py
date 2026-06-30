"""Code supporting the LabThings server.

LabThings wraps the `fastapi.FastAPI` application in a `~lt.ThingServer`, which
provides the tools to serve and manage `~lt.Thing` instances.

See the :ref:`tutorial` for examples of how to set up a `~lt.ThingServer`.
"""

import logging
import os
import warnings
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from types import MappingProxyType
from typing import Any, AsyncGenerator, Optional, TypeVar, overload

import uvicorn
from anyio.from_thread import BlockingPortal
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError
from typing_extensions import Self

from labthings_fastapi.actions import ActionManager
from labthings_fastapi.exceptions import GlobalLockBusyError
from labthings_fastapi.global_lock import GlobalLock
from labthings_fastapi.logs import configure_thing_logger
from labthings_fastapi.message_broker import MessageBroker
from labthings_fastapi.middleware.url_for import url_for_middleware

# `_thing_servers` is used as a global from `ThingServer.__init__`
from labthings_fastapi.outputs import blob
from labthings_fastapi.server.config_model import (
    ThingsConfig,
    ThingServerConfig,
)
from labthings_fastapi.server.config_model import (
    normalise_things_config as normalise_things_config,
)
from labthings_fastapi.thing import Thing
from labthings_fastapi.thing_description._model import ThingDescription
from labthings_fastapi.thing_server_interface import ThingServerInterface
from labthings_fastapi.thing_slots import ThingSlot
from labthings_fastapi.utilities import class_attributes

__all__ = ["ThingServer"]


ThingSubclass = TypeVar("ThingSubclass", bound=Thing)


LOGGER = logging.getLogger(__name__)


class ThingServer:
    """Use FastAPI to serve `~lt.Thing` instances.

    The `~lt.ThingServer` sets up a `fastapi.FastAPI` application and uses it
    to expose the capabilities of `~lt.Thing` instances over HTTP.

    There are several functions of a `~lt.ThingServer`:

    * Manage where settings are stored, to allow `~lt.Thing` instances to
      load and save their settings from disk.
    * Configure the server to allow cross-origin requests (required if
      we use a web app that is not served from the `~lt.ThingServer`).
    * Manage the threads used to run :ref:`actions`.
    * Manage :ref:`blobs` to allow binary data to be returned.
    * Allow threaded code to call functions in the event loop, by providing
      an `anyio.from_thread.BlockingPortal`.
    """

    @overload
    def __init__(self, config: ThingServerConfig, *, debug: bool = False) -> None: ...

    @overload
    def __init__(self, *, debug: bool = False, **kwargs: Any) -> None: ...

    def __init__(
        self,
        config: ThingServerConfig | None = None,
        *,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        r"""Initialise a LabThings server.

        The `~lt.ThingServer` is responsible for running the code in `~lt.Thing`
        instances, and making them available over the network. It should be configured
        by passing a `~lt.ThingServerConfig` object (or a dictionary that can
        be validated as a `~lt.ThingServerConfig` object).

        For convenience and backwards compatibility, if `config` is `None` the keyword
        arguments will be passed to `~lt.ThingServerConfig` instead. Keyword arguments
        may not be used if the `config` argument is used, and may be removed in the
        future.

        Setting up the `~lt.ThingServer` involves creating the underlying
        `fastapi.FastAPI` app, setting its lifespan function (used to
        set up and shut down the `~lt.Thing` instances), and configuring it
        to allow cross-origin requests.

        :param config: a `~lt.ThingServerConfig` object that configures the server,
            or something that may be converted to one.
        :param debug: ff ``True``, set the log level for `~lt.Thing` instances to
            DEBUG.
        :param \**kwargs: ff keyword arguments are supplied, they will be passed
            to the constructor of `~lt.ThingServerConfig`\ . This is not allowed
            if `config` is a `~lt.ThingServerConfig` object.

        :raises TypeError: if the value of `config` cannot be parsed as a
            `~lt.ThingServerConfig`\ .
        :raises ValueError: if keyword arguments are supplied together with `config`\ .
        """
        self.startup_failure: dict | None = None
        self._debug = debug
        # Note: this is safe to call multiple times.
        configure_thing_logger(logging.DEBUG if self._debug else None)
        if config is not None:
            try:
                self._config = ThingServerConfig.model_validate(config)
            except ValidationError as e:
                raise TypeError(
                    "The value passed to `ThingServer()` could not be validated as "
                    "a server configuration. If you are passing a dictionary of "
                    "Things, this must be done using `ThingServer.from_things` instead."
                ) from e
            if kwargs != {}:
                raise ValueError(
                    f"Extra keyword arguments supplied to `ThingServer()`: {kwargs}. "
                    "When a `ThingServerConfig` object is specified, no extra keyword "
                    "arguments may be supplied."
                )
        else:
            warnings.warn(
                DeprecationWarning(
                    "`ThingServer` should be initialised with the `config` parameter. "
                    "Taking configuration options from keyword arguments will be "
                    "removed in a future release."
                ),
                stacklevel=2,
            )
            self._config = ThingServerConfig(**kwargs)
        if self._config.settings_folder is None:
            self._config.settings_folder = "./settings"
        self.app = FastAPI(lifespan=self.lifespan, separate_input_output_schemas=False)
        self._set_cors_middleware()
        self._set_url_for_middleware()
        self._add_exception_handlers()
        self.action_manager = ActionManager()
        self.message_broker = MessageBroker()
        self.app.include_router(self.action_manager.router(), prefix=self.api_prefix)
        self.app.include_router(blob.router, prefix=self.api_prefix)
        self.app.include_router(self._things_view_router(), prefix=self.api_prefix)
        self.blocking_portal: Optional[BlockingPortal] = None
        self.startup_status: dict[str, str | dict] = {"things": {}}
        global _thing_servers  # noqa: F824
        self.global_lock = GlobalLock() if self._config.enable_global_lock else None
        # The function calls below create and set up the Things.
        self._things = self._create_things()
        self._connect_things()
        self._attach_things_to_server()

    @classmethod
    def from_things(
        cls,
        things: ThingsConfig,
        debug: bool = False,
        **kwargs: Any,
    ) -> Self:
        r"""Create a ThingServer using a dictionary of `~lt.Thing` subclasses.

        In test and example code, it's convenient to be able to pass server and
        `Thing` configurations as keyword arguments rather than a config model.

        This convenience method will turn its keyword arguments into a server
        configuration and create a server based on it.

        :param things: A mapping of names to `Thing` configurations. These may
            be specified as a `~lt.ThingConfig` object, a `~lt.Thing` subclass,
            or an import string referencing a `~lt.Thing` subclass.
        :param debug: Whether to start the server in debug mode.
        :param \**kwargs: Additional keyword arguments are passed to
            `~lt.ThingServerConfig`\ .
        :return: a `~lt.ThingServer` instance.
        """
        return cls(
            ThingServerConfig(
                things=things,
                **kwargs,
            ),
            debug=debug,
        )

    @classmethod
    def from_config(cls, config: ThingServerConfig, debug: bool = False) -> Self:
        r"""Create a ThingServer from a configuration model.

        This is equivalent to ``ThingServer(config, debug=debug)``\ .

        :param config: The configuration parameters for the server.
        :param debug: If ``True``, set the log level for `~lt.Thing` instances to
                      DEBUG.
        :return: A `~lt.ThingServer` configured as per the model.
        """
        warnings.warn(
            DeprecationWarning(
                "`ThingServer.from_config()` is redundant and will be removed in "
                "a future release. Use `ThingServer()` instead."
            ),
            stacklevel=2,
        )
        return cls(config, debug=debug)

    def _set_cors_middleware(self) -> None:
        """Configure the server to allow requests from other origins.

        This is required to allow web applications access to the HTTP API,
        if they are not served from the same origin (i.e. if they are not
        served as part of the `~lt.ThingServer`.).

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

    def _add_exception_handlers(self) -> None:
        """Add exception handlers to the FastAPI application."""

        @self.app.exception_handler(GlobalLockBusyError)
        async def global_lock_exception_handler(
            _request: Request, exc: GlobalLockBusyError
        ) -> JSONResponse:
            return JSONResponse(
                status_code=409,
                content={"detail": repr(exc)},
            )

        @self.app.exception_handler(PydanticSerializationError)
        async def serialisation_error_handler(
            request: Request, exc: PydanticSerializationError
        ) -> JSONResponse:
            LOGGER.error(
                f"Couldn't serialise response to {request.url} because of error: \n"
                f"{exc}"
            )
            return JSONResponse(status_code=500, content={"detail": str(exc)})

    @property
    def debug(self) -> bool:
        """Whether the server is in debug mode."""
        return self._debug

    @property
    def settings_folder(self) -> str:
        """The folder in which we will store `Thing` settings.

        :raises RuntimeError: if there is no settings folder set.
            This should never happen, as it's set in `__init__`.
        """
        if self._config.settings_folder is None:
            raise RuntimeError(
                "The settings folder should be set during initialisation. "
                "This may indicate a LabThings bug, or incorrect subclassing "
                "of `ThingServer`."
            )
        return self._config.settings_folder

    @property
    def things(self) -> Mapping[str, Thing]:
        """A read-only mapping of names to `~lt.Thing` instances."""
        return MappingProxyType(self._things)

    @property
    def application_config(self) -> Mapping[str, Any] | None:
        """The application configuration from the config file.

        :return: The custom configuration as specified in the configuration
            file.
        """
        return self._config.application_config

    @property
    def api_prefix(self) -> str:
        r"""A string that prefixes all URLs in the application.

        This will either be empty, or start with a slash and not
        end with a slash. Validation is performed in `~lt.ThingServerConfig`\ .
        """
        return self._config.api_prefix

    ThingInstance = TypeVar("ThingInstance", bound=Thing)

    def things_by_class(self, cls: type[ThingInstance]) -> Sequence[ThingInstance]:
        """Return all Things attached to this server matching a class.

        Return all instances of ``cls`` attached to this server.

        :param cls: A `~lt.Thing` subclass.

        :return: all instances of ``cls`` that have been added to this server.
        """
        return [t for t in self.things.values() if isinstance(t, cls)]

    def thing_by_class(self, cls: type[ThingInstance]) -> ThingInstance:
        """Return the instance of ``cls`` attached to this server.

        This function calls `.ThingServer.things_by_class`, but asserts that
        there is exactly one match.

        :param cls: a `~lt.Thing` subclass.

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
        return f"{self.api_prefix}/{name}/"

    def _create_things(self) -> Mapping[str, Thing]:
        r"""Create the Things, add them to the server, and connect them up if needed.

        This method is responsible for creating instances of `~lt.Thing` subclasses
        and adding them to the server. It also ensures the `~lt.Thing`\ s are connected
        together if required.

        The Things are defined in ``self._config.thing_configs`` which in turn is
        generated from the ``things`` argument to ``__init__``\ .

        :return: A mapping of names to `~lt.Thing` instances.

        :raise TypeError: if ``cls`` is not a subclass of `~lt.Thing`.
        """
        things: dict[str, Thing] = {}
        for name, config in self._config.thing_configs.items():
            if not issubclass(config.cls, Thing):
                raise TypeError(f"{config.cls} is not a Thing subclass.")
            interface = ThingServerInterface(
                name=name, class_name=config.cls.__name__, server=self
            )
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

        A `~lt.Thing` may have attributes defined as ``lt.thing_slot()``, which
        will be populated after all `~lt.Thing` instances are loaded on the server.

        This function is responsible for supplying the `~lt.Thing` instances required
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

        This calls `~lt.Thing.attach_to_server` on each `~lt.Thing` that is a part of
        this `~lt.ThingServer` in order to add the HTTP endpoints and load settings.
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

    def _things_view_router(self) -> APIRouter:
        """Create a router for the endpoint that shows the list of attached things.

        :returns: an APIRouter with the `thing_descriptions` endpoint.
        """
        router = APIRouter()
        thing_server = self

        @router.get(
            "/thing_descriptions/",
            response_model_exclude_none=True,
            response_model_by_alias=True,
        )
        def thing_descriptions(request: Request) -> Mapping[str, ThingDescription]:
            """Describe all the things available from this server.

            This returns a dictionary, where the keys are the paths to each
            `~lt.Thing` attached to the server, and the values are :ref:`wot_td`
            documents represented as `.ThingDescription` objects. These should enable
            clients to see all the capabilities of the `~lt.Thing` instances and
            access them over HTTP.

            :param request: is supplied automatically by FastAPI.

            :return: a dictionary mapping Thing paths to :ref:`wot_td` objects, which
                are `pydantic.BaseModel` subclasses that get serialised to
                dictionaries.
            """
            return {
                name: thing.thing_description(
                    path=f"{self.api_prefix}/{name}/", base=str(request.base_url)
                )
                for name, thing in thing_server.things.items()
            }

        @router.get("/things/")
        def thing_paths(request: Request) -> Mapping[str, str]:
            """URLs pointing to the Thing Descriptions of each Thing.

            :param request: is supplied automatically by FastAPI.

            :return: a list of paths pointing to `~lt.Thing` instances. These
                URLs will return the :ref:`wot_td` of one `~lt.Thing` each.
            """  # noqa: D403 (URLs is correct capitalisation)
            return {
                t: str(request.url_for(f"things.{t}"))
                for t in thing_server.things.keys()
            }

        return router

    def serve(self, host: str = "localhost", port: int = 5000) -> None:
        r"""Run the server in `uvicorn`\ .

        This method will run the server from Python, using `uvicorn.run`\ .
        This is the most convenient way to run a LabThings server from Python, and
        is identical to what happens when it is run from the command line.

        :param host: The IP address or hostname on which to serve. By default, this
            is ``localhost`` which is only accessible from your computer. To serve
            over a network on all available IPv4 addresses, use ``"0.0.0.0"``.
        :param port: The port on which to serve. This defaults to 5000.
        """
        uvicorn.run(self.app, host=host, port=port, ws="websockets-sansio")

    @contextmanager
    def test_client(self) -> Iterator[TestClient]:
        """A context manager to test out a server without binding to a port.

        This context manager will start up the server and run an event loop, but
        instead of responding to requests on a network port, it uses
        `fastapi.testclient.TestClient` to simulate HTTP requests.

        This is provided to simplify test code, and should not be used in production.

        :yields: a `fastapi.testclient.TestClient` to simulate HTTP requests.

        .. warning::

            Usually, a server is only started up and shut down once. Calling this
            method multiple times may have unexpected results.

            As a rule, only ever use this method in your test suite.
        """
        with TestClient(self.app) as client:
            yield client
