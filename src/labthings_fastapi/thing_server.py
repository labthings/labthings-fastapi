from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Optional
from fastapi import FastAPI
from anyio.from_thread import BlockingPortal
from contextlib import asynccontextmanager, AbstractContextManager, ExitStack
from .actions import ActionManager

if TYPE_CHECKING:
    from .thing import Thing

class ThingServer:
    def __init__(self, app: Optional[FastAPI]=None):
        self.app = app or FastAPI(lifespan=self.lifespan)
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
        thing.attach_to_server(self, path)

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        """Manage set up and tear down
        
        This does two important things:
        * It sets up the blocking portal so background threads can run async code
          (important for events)
        * It manages setup/teardown code for Things, if they are context managers
        """
        async with BlockingPortal() as portal:
            for thing in self.things:
                if thing._labthings_blocking_portal is not None:
                    raise RuntimeError("Things may only ever have one blocking portal")
                thing._labthings_blocking_portal = portal
            contextmanagers = [
                t for t in self.things 
                if isinstance(t, AbstractContextManager)
            ]
            with ExitStack() as stack:
                for thing in contextmanagers:
                    stack.enter_context(thing)
                yield
            for thing in self.things:
                thing._labthings_blocking_portal = None

