from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from fastapi import FastAPI
from .descriptors import ActionDescriptor, PropertyDescriptor

if TYPE_CHECKING:
    from .thing_server import ThingServer
    from .actions import ActionManager
class Thing:
    def attach_to_server(self, server: ThingServer, path: str):
        """Add HTTP handlers to an app for all Interaction Affordances"""
        self.path = path
        self.action_manager: ActionManager = server.action_manager

        cls = self.__class__
        for name in dir(cls):
            item = getattr(cls, name)
            try:
                item.add_to_fastapi(server.app, self)
            except AttributeError:
                # We try to add everything, and ignore whatever doesn't have
                # an `add_to_fastapi` method.
                # TODO: Do we want to be more choosy about what we add?
                pass
        