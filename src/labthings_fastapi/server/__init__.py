from __future__ import annotations
from typing import Optional, Sequence, TypeVar
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
from ..thing_description.model import ThingDescription
from ..dependencies.thing_server import _thing_servers
from ..outputs.blob import BlobDataManager

# A path should be made up of names separated by / as a path separator.
# Each name should be made of alphanumeric characters, hyphen, or underscore.
# This regex enforces a trailing /
PATH_REGEX = re.compile(r"^/([a-zA-Z0-9\-_]+\/)+$")


class ThingServer:
    def __init__(self, settings_folder: Optional[str] = None):
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
        global _thing_servers
        _thing_servers.add(self)

    app: FastAPI
    action_manager: ActionManager
    blob_data_manager: BlobDataManager

    def set_cors_middleware(self) -> None:
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @property
    def things(self) -> Mapping[str, Thing]:
        """Return a dictionary of all the things"""
        return MappingProxyType(self._things)

    ThingInstance = TypeVar("ThingInstance", bound=Thing)

    def things_by_class(self, cls: type[ThingInstance]) -> Sequence[ThingInstance]:
        """Return all Things attached to this server matching a class"""
        return [t for t in self.things.values() if isinstance(t, cls)]

    def thing_by_class(self, cls: type[ThingInstance]) -> ThingInstance:
        """The Thing attached to this server matching a given class.

        A RuntimeError will be raised if there is not exactly one matching Thing.
        """
        instances = self.things_by_class(cls)
        if len(instances) == 1:
            return instances[0]
        raise RuntimeError(
            f"There are {len(instances)} Things of class {cls}, expected 1."
        )

    def add_thing(self, thing: Thing, path: str):
        """Add a thing to the server

        :param thing: The thing to add to the server.
        :param path: the relative path to access the thing on the server. Must only
        contain alphanumeric characters, hyphens, or underscores.
        """
        # Ensure leading and trailing /
        if not path.endswith("/"):
            path += "/"
        if not path.startswith("/"):
            path = "/" + path
        if PATH_REGEX.match(path) is None:
            msg = (
                f"{path} contains unsafe characters. Use only alphanumeric "
                "characters, hyphens and underscores"
            )
            raise ValueError(msg)
        if path in self._things:
            raise KeyError(f"{path} has already been added to this thing server.")
        self._things[path] = thing
        settings_folder = os.path.join(self.settings_folder, path.lstrip("/"))
        os.makedirs(settings_folder, exist_ok=True)
        thing.attach_to_server(
            self, path, os.path.join(settings_folder, "settings.json")
        )

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """Manage set up and tear down

        This does two important things:

        * It sets up the blocking portal so background threads can run async code
          (important for events)
        * It runs setup/teardown code for Things.

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
            for name, thing in self.things.items():
                # Remove the blocking portal - the event loop is about to stop.
                thing._labthings_blocking_portal = None

        self.blocking_portal = None

    def add_things_view_to_app(self):
        """Add an endpoint that shows the list of attached things."""
        thing_server = self

        @self.app.get(
            "/thing_descriptions/",
            response_model_exclude_none=True,
            response_model_by_alias=True,
        )
        def thing_descriptions(request: Request) -> Mapping[str, ThingDescription]:
            """A dictionary of all the things available from this server"""
            return {
                path: thing.thing_description(path, base=str(request.base_url))
                for path, thing in thing_server.things.items()
            }

        @self.app.get("/things/")
        def thing_paths(request: Request) -> Mapping[str, str]:
            """URLs pointing to the Thing Descriptions of each Thing."""
            return {
                t: f"{str(request.base_url).rstrip('/')}{t}"
                for t in thing_server.things.keys()
            }


def server_from_config(config: dict) -> ThingServer:
    """Create a ThingServer from a configuration dictionary"""
    server = ThingServer(config.get("settings_folder", None))
    for path, thing in config.get("things", {}).items():
        if isinstance(thing, str):
            thing = {"class": thing}
        try:
            cls = object_reference_to_object(thing["class"])
        except ImportError as e:
            raise ImportError(
                f"Could not import {thing['class']}, which was "
                f"specified as the class for {path}. The error is "
                f"printed below:\n\n{e}"
            )
        try:
            instance = cls(*thing.get("args", {}), **thing.get("kwargs", {}))
        except Exception as e:
            raise e
        assert isinstance(instance, Thing), f"{thing['class']} is not a Thing"
        server.add_thing(instance, path)
    return server
