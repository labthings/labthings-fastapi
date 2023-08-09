from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Optional
from fastapi import FastAPI
from .actions import ActionManager

if TYPE_CHECKING:
    from .thing import Thing

class ThingServer:
    def __init__(self, app: Optional[FastAPI]=None):
        self.app = app or FastAPI()
        self.action_manager = ActionManager()
        self.action_manager.attach_to_app(self.app)
        self._things: dict[str, Thing] = {}

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
