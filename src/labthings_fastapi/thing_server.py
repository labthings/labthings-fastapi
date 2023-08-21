from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Optional
from fastapi import FastAPI
from anyio.from_thread import BlockingPortal
from contextlib import asynccontextmanager, AsyncExitStack
from .actions import ActionManager
from .thing_settings import ThingSettings
import os.path

if TYPE_CHECKING:
    from .thing import Thing

class ThingServer:
    def __init__(self, app: Optional[FastAPI]=None, settings_folder: str=None):
        self.app = app or FastAPI(lifespan=self.lifespan)
        self.settings_folder = settings_folder or "./settings"
        self.action_manager = ActionManager()
        self.action_manager.attach_to_app(self.app)
        self._things: dict[str, Thing] = {}
        self.blocking_portal: Optional[BlockingPortal] = None

    @property
    def things(self) -> Iterable[Thing]:
        """Return a dictionary of all the things"""
        return self._things.values()
    
    def add_thing(self, thing: Thing, path: str):
        """Add a thing to the server"""
        if not path.endswith("/"):
            path += "/"
        if path in self._things:
            raise KeyError(f"{path} has already been added to this thing server.")
        self._things[path] = thing
        # TODO: check for illegal things in `path` - potential security issue.
        settings_folder = os.path.join(self.settings_folder, path.lstrip("\\/"))  # path will start with "/"
        os.makedirs(settings_folder, exist_ok=True)
        thing._labthings_thing_settings = ThingSettings(os.path.join(settings_folder, "settings.json"))
        thing.attach_to_server(self, path)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """Manage set up and tear down
        
        This does two important things:
        * It sets up the blocking portal so background threads can run async code
          (important for events)
        * It runs setup/teardown code for Things.
        """
        async with BlockingPortal() as portal:
            # We attach a blocking portal to each thing, so that threaded code can
            # make callbacks to async code (needed for events etc.)
            for thing in self.things:
                if thing._labthings_blocking_portal is not None:
                    raise RuntimeError("Things may only ever have one blocking portal")
                thing._labthings_blocking_portal = portal
            # we __aenter__ and __aexit__ each Thing, which will in turn call the
            # synchronous __enter__ and __exit__ methods if they exist, to initialise
            # and shut down the hardware. NB we must make sure the blocking portal
            # is present when this happens, in case we are dealing with threads.
            async with AsyncExitStack() as stack:
                for thing in self.things:
                    await stack.enter_async_context(thing)
                yield
            for thing in self.things:
                # Remove the blocking portal - the event loop is about to stop.
                thing._labthings_blocking_portal = None
